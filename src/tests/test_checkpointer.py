"""Tests for checkpoint save/load — serialization roundtrip.

DB integration tests require a running PostgreSQL. The core serialization
test validates that ProjectState survives JSONB roundtrip without data loss.
"""

import json

from src.orchestrator.state import ProjectState, AgentStatus, Artifacts


def test_project_state_jsonb_roundtrip() -> None:
    """Verify ProjectState can be serialized to JSON and back without data loss."""
    original = ProjectState(
        user_id="user-123",
        initial_prompt="Build a CRUD API for task management",
        current_agent="database_agent",
        step_number=2,
        artifacts=Artifacts(
            db_schema_ddl="CREATE TABLE tasks (...)",
            api_spec_openapi={"/tasks": {"get": {"summary": "List tasks"}}},
            dependencies=["fastapi", "sqlalchemy"],
        ),
        iteration_counts={"database": 1, "backend": 0, "frontend": 0, "security": 0},
        error_log=["Warning: missing index on tasks.user_id"],
    )
    original.status = AgentStatus.RUNNING
    original.version = 3

    # Simulate JSONB: serialize to JSON string, then parse back
    serialized = original.model_dump_json()
    parsed = json.loads(serialized)
    restored = ProjectState.model_validate(parsed)

    # Assert all fields survive
    assert restored.user_id == original.user_id
    assert restored.initial_prompt == original.initial_prompt
    assert restored.current_agent == original.current_agent
    assert restored.step_number == original.step_number
    assert restored.version == original.version
    assert restored.status == original.status
    assert restored.artifacts.db_schema_ddl == original.artifacts.db_schema_ddl
    assert restored.artifacts.api_spec_openapi == original.artifacts.api_spec_openapi
    assert restored.artifacts.dependencies == original.artifacts.dependencies
    assert restored.iteration_counts == original.iteration_counts
    assert restored.error_log == original.error_log
    assert restored.project_id == original.project_id


def test_project_state_defaults() -> None:
    """Verify default values are set correctly."""
    state = ProjectState(user_id="u1", initial_prompt="hi")
    assert state.status == AgentStatus.PENDING
    assert state.current_agent == "orchestrator"
    assert state.step_number == 0
    assert state.version == 0
    assert state.artifacts.product_spec is None
    assert state.iteration_counts == {"database": 0, "backend": 0, "frontend": 0, "security": 0}


def test_project_state_status_transitions() -> None:
    """Verify status enum works as expected."""
    state = ProjectState(user_id="u1", initial_prompt="test")
    assert AgentStatus.PENDING.value == "pending"
    assert AgentStatus.RUNNING.value == "running"
    assert AgentStatus.SUCCESS.value == "success"
    assert AgentStatus.FAILED.value == "failed"
    assert AgentStatus.INTERVENTION_NEEDED.value == "intervention_needed"
    assert AgentStatus.PAUSED.value == "paused"
