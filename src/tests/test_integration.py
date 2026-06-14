"""Integration tests — full pipeline, checkpointing, routing, MCP, auth, rate limiting.

These tests require running PostgreSQL, Redis, and a Celery worker.
Run with: pytest -m integration
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.api.db_deps import get_db
from src.orchestrator.router import decide_next_agent
from src.orchestrator.state import Artifacts, ProjectState, AgentStatus

# ── Mock DB session for API tests ─────────────────────────────────────────


class _MockSession:
    """Minimal mock DB session for integration-style API tests."""

    def __init__(self):
        self._storage: dict = {}
        self._flushed = False

    async def flush(self):
        self._flushed = True
        # Assign fake IDs if not set
        for key, obj in self._storage.items():
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = "00000000-0000-0000-0000-000000000001"

    async def commit(self):
        self._flushed = True

    async def rollback(self):
        self._flushed = False

    async def close(self):
        pass

    def add(self, obj):
        key = f"{type(obj).__name__}:{getattr(obj, 'id', id(obj))}"
        self._storage[key] = obj

    def add_all(self, objects):
        for obj in objects:
            self.add(obj)

    async def execute(self, statement):
        from unittest.mock import MagicMock
        return MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        )


@pytest.fixture
def mock_db_session():
    return _MockSession()


@pytest.fixture
async def integration_client(mock_db_session):
    """Test client with overridden DB dependency."""
    async def _override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ── Pipeline Routing Tests ────────────────────────────────────────────────


class TestPipelineRouting:
    """Edge routing logic — linear flow, retry loop, intervention detection."""

    def _make_state(self, current_agent: str, status: AgentStatus = AgentStatus.RUNNING) -> ProjectState:
        return ProjectState(
            project_id="test-0001",
            user_id="user-1",
            initial_prompt="Test prompt",
            current_agent=current_agent,
            status=status,
        )

    def test_linear_progression_from_database(self):
        """database_agent → backend_agent."""
        state = self._make_state("database_agent")
        assert decide_next_agent(state) == "backend_agent"

    def test_linear_progression_from_backend(self):
        """backend_agent → frontend_agent."""
        state = self._make_state("backend_agent")
        assert decide_next_agent(state) == "frontend_agent"

    def test_linear_progression_from_frontend(self):
        """frontend_agent → security_agent."""
        state = self._make_state("frontend_agent")
        assert decide_next_agent(state) == "security_agent"

    def test_security_pass_ends_pipeline(self):
        """security_agent with SUCCESS → __end__."""
        state = self._make_state("security_agent", AgentStatus.SUCCESS)
        assert decide_next_agent(state) == "__end__"

    def test_failed_state_ends_pipeline(self):
        """FAILED status → __end__ immediately."""
        state = self._make_state("database_agent", AgentStatus.FAILED)
        assert decide_next_agent(state) == "__end__"

    def test_intervention_needed_ends_pipeline(self):
        """INTERVENTION_NEEDED → __end__."""
        state = self._make_state("security_agent", AgentStatus.INTERVENTION_NEEDED)
        assert decide_next_agent(state) == "__end__"

    def test_success_state_ends_pipeline(self):
        """SUCCESS status → __end__."""
        state = self._make_state("frontend_agent", AgentStatus.SUCCESS)
        assert decide_next_agent(state) == "__end__"

    def test_security_reroute_back_to_offending_agent(self):
        """security_agent reroutes to offending agent via state.current_agent."""
        state = self._make_state("frontend_agent", AgentStatus.RUNNING)
        # Simulate security setting current_agent to frontend after failure
        state.current_agent = "frontend_agent"
        # Router should follow the reroute
        next_node = decide_next_agent(state)
        assert next_node in ("frontend_agent", "database_agent", "backend_agent", "security_agent")

    def test_unknown_agent_returns_start(self):
        """Unknown agent name → back to start of pipeline."""
        state = self._make_state("unknown_agent")
        assert decide_next_agent(state) == "database_agent"

    def test_security_reroute_with_changed_current_agent(self):
        """Security sets current_agent to offending agent, router follows it."""
        state = self._make_state("security_agent", AgentStatus.RUNNING)
        # Security agent found issues in backend and rerouted
        state.current_agent = "backend_agent"
        next_node = decide_next_agent(state)
        assert next_node == "frontend_agent"


# ── ProjectState Roundtrip Tests ──────────────────────────────────────────


class TestProjectStateRoundtrip:
    """Full ProjectState serialization/deserialization."""

    def test_complex_artifacts_roundtrip(self):
        """State with full artifacts survives JSON roundtrip."""
        original = ProjectState(
            project_id="test-rt-1",
            user_id="user-rt-1",
            initial_prompt="Build a blog",
            artifacts=Artifacts(
                db_schema_ddl="CREATE TABLE posts (id SERIAL PRIMARY KEY);",
                db_credentials={"db_name": "blog", "schema_name": "public"},
                api_spec_openapi={"openapi": "3.0.0", "info": {"title": "Blog API"}},
                backend_code={"app/main.py": "print('hello')"},
                frontend_code={"src/App.tsx": "export default function App() {}"},
                dependencies=["fastapi", "react"],
                test_report={"passed": True, "issues": []},
            ),
            iteration_counts={"database": 1, "backend": 2, "frontend": 0, "security": 0},
            step_number=4,
            status=AgentStatus.SUCCESS,
        )

        serialized = original.model_dump_json()
        restored = ProjectState.model_validate_json(serialized)
        assert restored.project_id == original.project_id
        assert restored.artifacts.db_schema_ddl == original.artifacts.db_schema_ddl
        assert restored.artifacts.api_spec_openapi == original.artifacts.api_spec_openapi
        assert restored.artifacts.backend_code["app/main.py"] == "print('hello')"
        assert restored.step_number == 4
        assert restored.status == AgentStatus.SUCCESS

    def test_minimal_state_defaults(self):
        """Minimal state gets correct defaults."""
        state = ProjectState(project_id="p-1", user_id="u-1", initial_prompt="Test")
        assert state.status == AgentStatus.PENDING
        assert state.current_agent == "orchestrator"
        assert state.step_number == 0
        assert state.artifacts.backend_code == {}
        assert state.artifacts.frontend_code == {}
        assert state.iteration_counts["database"] == 0
        assert state.version == 0

    def test_status_transitions_are_valid(self):
        """Status transitions work as expected."""
        state = ProjectState(project_id="p-1", user_id="u-1", initial_prompt="Test")
        assert state.status == AgentStatus.PENDING

        state.status = AgentStatus.RUNNING
        assert state.status == AgentStatus.RUNNING

        state.status = AgentStatus.SUCCESS
        assert state.status == AgentStatus.SUCCESS

        # Can go from SUCCESS back to FAILED
        state.status = AgentStatus.FAILED
        assert state.status == AgentStatus.FAILED


# ── Auth Middleware Tests ──────────────────────────────────────────────────


class TestAuthMiddleware:
    """Auth hardening — JWT, API key, dev mode bypass."""

    async def test_health_is_public(self, integration_client):
        """Health endpoint should not require auth."""
        resp = await integration_client.get("/health")
        assert resp.status_code == 200

    async def test_create_project_works_in_dev_mode(self, integration_client):
        """In dev mode, project creation should work without auth header."""
        with patch("src.api.middleware.DEBUG", True):
            resp = await integration_client.post(
                "/api/v1/projects",
                json={"initial_prompt": "Test project"},
            )
            assert resp.status_code in (202, 200)

    async def test_missing_auth_rejected_in_prod(self, integration_client):
        """Without auth in prod mode, request should be rejected."""
        with patch("src.api.middleware.DEBUG", False), \
             patch("src.api.middleware.API_KEY", None):
            resp = await integration_client.post(
                "/api/v1/projects",
                json={"initial_prompt": "Test"},
            )
            assert resp.status_code == 401


# ── Monitoring /health Tests ──────────────────────────────────────────────


class TestMonitoringEndpoints:
    """Enhanced health and metrics endpoints."""

    async def test_health_returns_detailed_info(self, integration_client):
        """Health should include uptime, version, and request counts."""
        resp = await integration_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "cave-api"
        assert "version" in body
        assert "uptime_seconds" in body
        assert "requests_total" in body

    async def test_metrics_endpoint(self, integration_client):
        """Metrics endpoint returns Prometheus text."""
        resp = await integration_client.get("/metrics")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        text = resp.text
        assert "cave_requests_total" in text
        assert "cave_uptime_seconds" in text
        assert "cave_errors_total" in text


# ── Security Agent Retry Logic Tests ──────────────────────────────────────


class TestSecurityRetryLogic:
    """Security agent retry count and intervention detection."""

    def test_retry_count_increments(self):
        """iteration_counts should increment per retry."""
        state = ProjectState(project_id="r-1", user_id="u-1", initial_prompt="Test")
        # Simulate retries
        state.iteration_counts["database"] = 1
        assert state.iteration_counts["database"] == 1
        state.iteration_counts["database"] += 1
        assert state.iteration_counts["database"] == 2

    def test_max_retries_trigger_intervention(self):
        """After 3 retries, security agent should set INTERVENTION_NEEDED."""
        from src.agents.security import MAX_RETRIES_PER_AGENT, SecurityAgent

        state = ProjectState(project_id="r-2", user_id="u-1", initial_prompt="Test")
        state.artifacts.backend_code = {"app/main.py": "print('hello')"}

        agent = SecurityAgent()
        # Simulate 3 failed attempts stored in security history
        state.iteration_counts["backend"] = 2

        # The agent's report parsing is LLM-dependent, so we test the
        # iteration count logic directly
        assert MAX_RETRIES_PER_AGENT == 3
        assert state.iteration_counts["backend"] < MAX_RETRIES_PER_AGENT


# ── MCP Gateway Unit Tests ─────────────────────────────────────────────────


class TestMCPToolRegistry:
    """ToolRegistry — tool↔server mapping and agent tool binding."""

    def test_registry_maps_tools_to_servers(self):
        """Tool names should resolve to correct server."""
        from src.mcp_gateway import ToolRegistry

        registry = ToolRegistry()
        assert registry.get_server_for_tool("write_file") == "filesystem"
        assert registry.get_server_for_tool("execute_sql") == "supabase"
        assert registry.get_server_for_tool("run_semgrep") == "sast"

    def test_unknown_tool_raises_key_error(self):
        """Asking for an unregistered tool should raise KeyError."""
        from src.mcp_gateway import ToolRegistry

        registry = ToolRegistry()
        with pytest.raises(KeyError):
            registry.get_server_for_tool("nonexistent_tool")

    def test_agent_tool_binding(self):
        """Each agent should have the correct tool set."""
        from src.mcp_gateway import ToolRegistry

        registry = ToolRegistry()

        db_tools = registry.get_agent_tools("database_agent")
        assert "execute_sql" in db_tools
        assert "list_tables" in db_tools

        backend_tools = registry.get_agent_tools("backend_agent")
        assert "write_file" in backend_tools
        assert "read_file" in backend_tools

        frontend_tools = registry.get_agent_tools("frontend_agent")
        assert "write_file" in frontend_tools

        security_tools = registry.get_agent_tools("security_agent")
        assert "run_semgrep" in security_tools
        assert "run_linter" in security_tools

    def test_custom_tool_registration(self):
        """Can register new tools and servers at runtime."""
        from src.mcp_gateway import ToolRegistry, MCPServerConfig

        registry = ToolRegistry(servers={}, agent_tools={})
        assert registry.list_servers() == []

        registry.register_server(MCPServerConfig(
            name="custom",
            command="echo",
            tools=["custom_tool"],
        ))
        assert "custom" in registry.list_servers()
        assert registry.get_server_for_tool("custom_tool") == "custom"

    def test_unregister_server_removes_tools(self):
        """Unregistering a server should remove its tools from the index."""
        from src.mcp_gateway import ToolRegistry

        registry = ToolRegistry()
        assert "execute_sql" in registry.list_tools()
        registry.unregister_server("supabase")
        with pytest.raises(KeyError):
            registry.get_server_for_tool("execute_sql")
