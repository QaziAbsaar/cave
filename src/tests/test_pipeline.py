"""End-to-end smoke tests for the project submission and pipeline flow.

Unit tests (no external deps):
    - POST /api/v1/projects returns 202 with correct shape
    - GET /api/v1/projects/{id} returns 404 for missing project
    - Request validation rejects bad input
    - Pause/resume endpoints return correct status

Integration tests (require Postgres + Redis + Celery):
    - Marked with @pytest.mark.integration
    - Run with: pytest -m integration
"""

import pytest
from httpx import AsyncClient


# ── Unit Tests (no external deps required) ───────────────────────


class TestCreateProject:
    """Tests for POST /api/v1/projects."""

    @pytest.mark.asyncio
    async def test_create_project_returns_202(self, client: AsyncClient) -> None:
        """Submit a valid project brief → 202 + project_id + ws_url."""
        resp = await client.post(
            "/api/v1/projects",
            json={"initial_prompt": "Build a todo app with FastAPI and React"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "project_id" in body
        assert "ws_url" in body
        assert body["ws_url"].startswith("/ws/projects/")
        assert body["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_project_with_title(self, client: AsyncClient) -> None:
        """Submit with optional title → 202."""
        resp = await client.post(
            "/api/v1/projects",
            json={
                "initial_prompt": "Build a blog",
                "title": "My Blog Project",
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "project_id" in body

    @pytest.mark.asyncio
    async def test_create_project_empty_prompt_rejected(self, client: AsyncClient) -> None:
        """Empty prompt → 422 validation error."""
        resp = await client.post(
            "/api/v1/projects",
            json={"initial_prompt": ""},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_missing_prompt_rejected(self, client: AsyncClient) -> None:
        """Missing initial_prompt field → 422."""
        resp = await client.post(
            "/api/v1/projects",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_long_prompt_rejected(self, client: AsyncClient) -> None:
        """Prompt over 2000 chars → 422."""
        long_prompt = "x" * 2001
        resp = await client.post(
            "/api/v1/projects",
            json={"initial_prompt": long_prompt},
        )
        assert resp.status_code == 422


class TestGetProject:
    """Tests for GET /api/v1/projects/{id}."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_returns_404(self, client: AsyncClient) -> None:
        """Unknown project_id → 404."""
        resp = await client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000",
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_project_invalid_uuid_returns_400(self, client: AsyncClient) -> None:
        """Malformed project_id → 400."""
        resp = await client.get("/api/v1/projects/not-a-uuid")
        assert resp.status_code == 400


class TestPauseResume:
    """Tests for pause/resume endpoints."""

    @pytest.mark.asyncio
    async def test_pause_nonexistent_project_returns_404(self, client: AsyncClient) -> None:
        """Pause unknown project → 404."""
        resp = await client.post(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000/pause",
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_nonexistent_project_returns_404(self, client: AsyncClient) -> None:
        """Resume unknown project → 404."""
        resp = await client.post(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000/resume",
        )
        assert resp.status_code == 404


class TestHealth:
    """Tests for the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        """GET /health → 200 with status ok."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "cave-api"


# ── Integration Tests (require Postgres + Redis + Celery) ────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_with_real_services():
    """Full end-to-end test: submit → WebSocket → 4 events → checkpoints → success.

    Requires: running PostgreSQL, Redis, and a Celery worker.
    Marked with @pytest.mark.integration.

    Run: pytest -m integration --asyncio-mode=auto
    """
    import asyncpg
    import httpx

    BASE_URL = "http://localhost:8000"

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. Submit project
        resp = await client.post(
            "/api/v1/projects",
            json={"initial_prompt": "Integration test project"},
        )
        assert resp.status_code == 202
        body = resp.json()
        project_id = body["project_id"]
        ws_url = body["ws_url"]

    # 2. Connect to WebSocket
    import asyncio
    import json

    events: list[dict] = []
    ws_target = f"ws://localhost:8000{ws_url}"

    async def listen_ws():
        try:
            import websockets
            async with websockets.connect(ws_target) as ws:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    events.append(json.loads(msg))
                    # Stop after project_completed
                    if any(e.get("event") == "project_completed" for e in events):
                        break
        except (Exception, asyncio.TimeoutError):
            pass

    # Give worker time to pick up the task (runs in background)
    await asyncio.sleep(1)
    ws_task = asyncio.create_task(listen_ws())

    # 3. Wait for events or timeout
    try:
        await asyncio.wait_for(ws_task, timeout=60)
    except asyncio.TimeoutError:
        pass

    # 4. Verify events
    event_types = [e["event"] for e in events]
    assert "agent_started" in event_types, f"No agent_started events: {event_types}"
    assert "agent_completed" in event_types, f"No agent_completed events: {event_types}"
    assert "project_completed" in event_types, f"No project_completed event: {event_types}"

    # 5. Verify checkpoints in DB
    conn = await asyncpg.connect(
        dsn="postgresql://cave:cave_dev@localhost:5432/cave"
    )
    try:
        row = await conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM project_checkpoints WHERE project_id = $1",
            project_id,
        )
        assert row["cnt"] >= 4, f"Expected >=4 checkpoints, got {row['cnt']}"
    finally:
        await conn.close()

    # 6. Verify final status
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.get(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success", f"Expected success, got {body['status']}"
