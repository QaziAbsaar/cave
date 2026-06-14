"""ProjectState schema — single source of truth for all agent pipeline data."""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from enum import Enum
import uuid


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    INTERVENTION_NEEDED = "intervention_needed"
    PAUSED = "paused"


class Artifacts(BaseModel):
    product_spec: Optional[str] = None
    db_schema_ddl: Optional[str] = None
    db_credentials: Dict[str, str] = Field(default_factory=dict)
    api_spec_openapi: Optional[dict] = None
    backend_code: Dict[str, str] = Field(default_factory=dict)
    frontend_code: Dict[str, str] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    test_report: Optional[dict] = None


class AgentIteration(BaseModel):
    agent: str
    attempt: int
    feedback: Optional[str] = None
    timestamp: str


class ProjectState(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    initial_prompt: str
    current_agent: str = "orchestrator"
    step_number: int = 0
    artifacts: Artifacts = Field(default_factory=Artifacts)
    iteration_counts: Dict[str, int] = Field(
        default_factory=lambda: {"database": 0, "backend": 0, "frontend": 0, "security": 0}
    )
    security_history: List[AgentIteration] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.PENDING
    error_log: List[str] = Field(default_factory=list)
    langfuse_trace_id: Optional[str] = None
    model_config_id: Optional[str] = None  # which model config to use
    version: int = 0  # incremented on every checkpoint save
