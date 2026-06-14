"""Celery worker — receives project submissions and runs the LangGraph pipeline.

Supports crash recovery via load_latest_checkpoint and Langfuse observability.
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional
from uuid import UUID

from celery import Celery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.database import engine
from src.api.models import Project
from src.orchestrator.checkpointer import (
    save_checkpoint,
    load_latest_checkpoint,
    get_connection,
)
from src.orchestrator.graph import build_graph, set_checkpoint_callback, set_mcp_gateway
from src.orchestrator.state import ProjectState, AgentStatus
from src.mcp_gateway import MCPGateway, ToolRegistry

logger = logging.getLogger(__name__)

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "cave",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


def _publish_error(project_id: str, message: str) -> None:
    """Publish an error event to the project's Redis channel."""
    import redis as sync_redis
    try:
        r = sync_redis.from_url(REDIS_URL)
        r.publish(
            f"project:{project_id}",
            json.dumps({
                "event": "error",
                "project_id": project_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "data": {"message": message, "recoverable": True},
            }),
        )
    except Exception:
        pass


async def _load_project_from_db(project_id: str) -> tuple[Project, AsyncSession]:
    """Load a Project record from the DB."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    try:
        result = await session.execute(
            select(Project).where(Project.id == UUID(project_id))
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        return project, session
    except Exception:
        await session.close()
        raise


async def _build_initial_state(project: Project) -> ProjectState:
    """Build a fresh ProjectState, checking for existing checkpoints for recovery.

    If a checkpoint exists (crash recovery), loads latest instead of creating fresh.
    """
    conn = await get_connection()
    try:
        latest = await load_latest_checkpoint(str(project.id), conn)
        if latest is not None:
            logger.info(
                "Crash recovery: resuming project %s from checkpoint v%d",
                project.id,
                latest.version,
            )
            latest.status = AgentStatus.RUNNING
            return latest
    except Exception:
        logger.info("No checkpoint found for %s — starting fresh", project.id)
    finally:
        await conn.close()

    # Fresh start
    return ProjectState(
        project_id=str(project.id),
        user_id=str(project.user_id),
        initial_prompt=project.initial_prompt,
    )


async def _run_pipeline(project_id: str) -> dict:
    """Async core: load project, run graph with checkpointing, update status."""
    project, db_session = await _load_project_from_db(project_id)

    # Build or recover state
    state = await _build_initial_state(project)
    state.status = AgentStatus.RUNNING

    # Update project status in DB
    project.status = "running"
    await db_session.commit()

    # Open a direct asyncpg connection for checkpoints
    checkpointer_conn = await get_connection()

    # Define checkpoint callback (called by agents in the graph)
    def checkpoint_cb(s: ProjectState) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(save_checkpoint(s, checkpointer_conn))

    set_checkpoint_callback(checkpoint_cb)

    # ── Phase 3: Create MCP Gateway ───────────────────────────────────
    gateway: Optional[MCPGateway] = None
    try:
        registry = ToolRegistry()
        gateway = MCPGateway(registry)
        await gateway.start_all()
        set_mcp_gateway(gateway)
        logger.info("MCP Gateway initialized for project %s", project_id)
    except Exception as gw_err:
        logger.warning(
            "MCP Gateway initialization failed (continuing without MCP): %s",
            gw_err,
        )
    # ──────────────────────────────────────────────────────────────────

    try:
        # Build and run the graph with Langfuse tracing
        graph = build_graph()

        config = {
            "recursion_limit": 15,  # Cost safety guardrail — NEVER remove
        }

        # Wire Langfuse CallbackHandler if keys are configured
        langfuse_pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        langfuse_sk = os.getenv("LANGFUSE_SECRET_KEY", "")
        if langfuse_pk and langfuse_sk:
            try:
                from langfuse.langchain import CallbackHandler

                handler = CallbackHandler(
                    user_id=state.user_id,
                    session_id=state.project_id,
                    trace_name="cave-agent-run",
                )
                config["callbacks"] = [handler]
            except Exception as exc:
                logger.warning("Failed to init Langfuse handler: %s", exc)

        # Invoke the graph
        final_state = await graph.ainvoke(state.model_dump(), config)
        result = ProjectState.model_validate(final_state)

        # Store trace ID if Langfuse was used
        if langfuse_pk and langfuse_sk:
            try:
                result.langfuse_trace_id = state.project_id  # simplified trace tracking
            except Exception:
                pass

        # Update project status
        project.status = result.status.value if isinstance(result.status, AgentStatus) else result.status
        project.current_agent = result.current_agent
        await db_session.commit()

        logger.info(
            "Pipeline done: project=%s status=%s steps=%d",
            project_id, project.status, result.step_number,
        )

        return {
            "project_id": project_id,
            "status": project.status,
            "step_number": result.step_number,
        }

    except Exception as exc:
        logger.exception("Pipeline error: project=%s", project_id)
        await db_session.rollback()
        project.status = "failed"
        await db_session.commit()
        raise

    finally:
        # Phase 3: shut down MCP gateway
        if gateway is not None:
            try:
                await gateway.shutdown()
            except Exception as gw_err:
                logger.warning("MCP Gateway shutdown error: %s", gw_err)
        await checkpointer_conn.close()
        await db_session.close()


@celery_app.task(bind=True, max_retries=3)
def run_project(self, project_id: str) -> dict:
    """Entry point task: runs the full agent pipeline for a project.

    Args:
        project_id: UUID string identifying the project.

    Returns:
        Dict with project_id and final status.
    """
    logger.info("run_project started: project=%s", project_id)

    try:
        result = asyncio.run(_run_pipeline(project_id))
        return result

    except Exception as exc:
        logger.exception("run_project failed: project=%s", project_id)
        _publish_error(project_id, str(exc))
        raise self.retry(exc=exc, countdown=10)
