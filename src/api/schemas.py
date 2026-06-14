"""Pydantic request/response schemas for the API."""

from pydantic import BaseModel, Field
from typing import Optional


class CreateProjectRequest(BaseModel):
    """Request body for POST /api/v1/projects."""

    initial_prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Plain-language brief describing the application to build",
    )
    title: Optional[str] = Field(
        None,
        max_length=200,
        description="Optional project title",
    )


class CreateProjectResponse(BaseModel):
    """Response body for POST /api/v1/projects (202 Accepted)."""

    project_id: str
    ws_url: str
    status: str = "pending"


class ProjectStatusResponse(BaseModel):
    """Response body for GET /api/v1/projects/{id}."""

    project_id: str
    status: str
    current_agent: Optional[str] = None
    step_number: int = 0


class PauseResumeResponse(BaseModel):
    """Response body for pause/resume endpoints."""

    project_id: str
    status: str
