"""Project CRUD routes — real implementation for Phase 1."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db_deps import get_db
from src.api.middleware import get_current_user
from src.api.models import Project, User
from src.api.schemas import (
    CreateProjectRequest,
    CreateProjectResponse,
    ProjectStatusResponse,
    PauseResumeResponse,
)
from src.orchestrator.state import ProjectState, AgentStatus
from src.worker import run_project

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """Return existing User or create a new one with the given ID."""
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            id=UUID(user_id),
            email=f"{user_id}@placeholder.local",
            hashed_password="",
            credits=100,
            tier="free",
        )
        db.add(user)
        await db.flush()
        logger.info("Created placeholder user: %s", user_id)
    return user


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_project(
    body: CreateProjectRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateProjectResponse:
    """Submit a new project brief.

    Validates input, creates DB records, pushes task to Celery queue.
    Returns 202 with project_id and WebSocket URL for progress streaming.
    """
    # Ensure user exists
    user = await _get_or_create_user(db, user_id)

    # Create Project record
    project = Project(
        user_id=user.id,
        title=body.title,
        initial_prompt=body.initial_prompt,
        status="pending",
    )
    db.add(project)
    await db.flush()

    # Create initial ProjectState
    state = ProjectState(
        project_id=str(project.id),
        user_id=str(user.id),
        initial_prompt=body.initial_prompt,
    )

    # Push to Celery queue
    run_project.delay(str(project.id))

    logger.info(
        "Project created: id=%s user=%s prompt_len=%d",
        project.id, user_id, len(body.initial_prompt),
    )

    return CreateProjectResponse(
        project_id=str(project.id),
        ws_url=f"/ws/projects/{project.id}",
        status="pending",
    )


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectStatusResponse:
    """Get project status and current state from DB."""
    try:
        pid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    result = await db.execute(select(Project).where(Project.id == pid))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectStatusResponse(
        project_id=str(project.id),
        status=project.status,
        current_agent=project.current_agent,
        step_number=0,
    )


@router.post("/{project_id}/pause")
async def pause_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PauseResumeResponse:
    """Pause execution after current agent completes."""
    try:
        pid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    result = await db.execute(select(Project).where(Project.id == pid))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project.status = "paused"
    logger.info("Project paused: %s", project_id)

    return PauseResumeResponse(project_id=project_id, status="paused")


@router.post("/{project_id}/resume")
async def resume_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PauseResumeResponse:
    """Resume execution from latest checkpoint."""
    try:
        pid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    result = await db.execute(select(Project).where(Project.id == pid))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project.status = "running"

    # Re-push to Celery (checkpointer will resume from latest checkpoint)
    run_project.delay(str(project.id))

    logger.info("Project resumed: %s", project_id)

    return PauseResumeResponse(project_id=project_id, status="running")
