"""LangGraph DAG definition — 4-agent pipeline with mock nodes.

Phase 1: mock agents sleep 2s, publish events, and save checkpoints.
Real agent prompts come in Phase 2.
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any, Optional

from langgraph.graph import END, StateGraph

from src.orchestrator.state import ProjectState, AgentStatus
from src.orchestrator.router import decide_next_agent

logger = logging.getLogger(__name__)

REDIS_PUBSUB_URL: str = os.getenv("REDIS_PUBSUB_URL", "redis://localhost:6379/1")

# Optional checkpoint callback injected by the worker
_save_checkpoint_cb: Optional[Callable[[ProjectState], None]] = None


def set_checkpoint_callback(cb: Callable[[ProjectState], None]) -> None:
    """Inject a checkpoint save callback into the graph runner.

    Called by the worker after constructing the graph. Each mock agent
    node invokes this after completing its simulated work.
    """
    global _save_checkpoint_cb
    _save_checkpoint_cb = cb


def _publish_event(project_id: str, event: str, data: dict[str, Any]) -> None:
    """Publish a progress event to the Redis pub/sub channel for this project."""
    import redis as sync_redis
    try:
        r = sync_redis.from_url(REDIS_PUBSUB_URL)
        r.publish(
            f"project:{project_id}",
            json.dumps({
                "event": event,
                "project_id": project_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "data": data,
            }),
        )
    except Exception as exc:
        logger.warning("Redis pub unavailable (event=%s project=%s): %s", event, project_id, exc)


async def _mock_agent_run(state: ProjectState, agent_name: str) -> ProjectState:
    """Simulate an agent run: sleep, publish events, update state, checkpoint."""
    project_id = state.project_id

    # Notify: agent started
    _publish_event(project_id, "agent_started", {"agent": agent_name, "step": state.step_number + 1})

    # Simulate work
    await asyncio.sleep(2)

    # Update state
    state.current_agent = agent_name
    state.step_number += 1

    # Save checkpoint after this agent
    if _save_checkpoint_cb is not None:
        _save_checkpoint_cb(state)
        _publish_event(project_id, "checkpoint_saved", {"version": state.version})

    # Notify: agent completed
    _publish_event(project_id, "agent_completed", {"agent": agent_name, "step": state.step_number})

    return state


# ---- Mock agent node functions ----


async def database_agent(state: ProjectState) -> ProjectState:
    """Mock Database Agent node."""
    return await _mock_agent_run(state, "database_agent")


async def backend_agent(state: ProjectState) -> ProjectState:
    """Mock Backend Agent node."""
    return await _mock_agent_run(state, "backend_agent")


async def frontend_agent(state: ProjectState) -> ProjectState:
    """Mock Frontend Agent node."""
    return await _mock_agent_run(state, "frontend_agent")


async def security_agent(state: ProjectState) -> ProjectState:
    """Mock Security/QA Agent node — also marks the project as success."""
    state = await _mock_agent_run(state, "security_agent")
    state.status = AgentStatus.SUCCESS
    _publish_event(state.project_id, "project_completed", {
        "download_url": "",
        "total_cost": 0.0,
    })
    return state


# ---- Build the graph ----


def build_graph() -> StateGraph:
    """Construct and compile the agent pipeline graph.

    Returns:
        A compiled LangGraph StateGraph that accepts and returns ProjectState.
    """
    workflow = StateGraph(ProjectState)

    # Register nodes
    workflow.add_node("database_agent", database_agent)
    workflow.add_node("backend_agent", backend_agent)
    workflow.add_node("frontend_agent", frontend_agent)
    workflow.add_node("security_agent", security_agent)

    # Entry point
    workflow.set_entry_point("database_agent")

    # Edges — route via decide_next_agent
    for agent_node in ("database_agent", "backend_agent", "frontend_agent", "security_agent"):
        workflow.add_conditional_edges(agent_node, decide_next_agent)

    return workflow.compile()
