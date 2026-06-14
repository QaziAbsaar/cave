"""pytest fixtures and FastAPI dependency overrides for testing."""

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.api.db_deps import get_db


# ── Mock DB Session ──────────────────────────────────────────────

class MockAsyncSession:
    """In-memory mock of an async SQLAlchemy session for testing."""

    def __init__(self) -> None:
        self._storage: dict = {}
        self._flushed: bool = False

    async def flush(self) -> None:
        self._flushed = True

    async def commit(self) -> None:
        self._flushed = True

    async def rollback(self) -> None:
        self._flushed = False

    async def close(self) -> None:
        pass

    def add(self, obj) -> None:
        key = f"{type(obj).__name__}:{getattr(obj, 'id', id(obj))}"
        self._storage[key] = obj

    def add_all(self, objects: list) -> None:
        for obj in objects:
            self.add(obj)

    async def execute(self, statement):
        """Return empty result for any query."""
        return MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
            scalars=MagicMock(return_value=MagicMock(
                all=MagicMock(return_value=[])
            )),
        )


@pytest.fixture
def mock_db() -> MockAsyncSession:
    """Return a shared mock DB session instance."""
    return MockAsyncSession()


@pytest.fixture
async def test_app(mock_db: MockAsyncSession) -> FastAPI:
    """Return the FastAPI app with DB dependency overridden to mock."""
    async def _override_get_db() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Return an async HTTP test client against the overridden app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Mock Celery Task ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_celery() -> MagicMock:
    """Prevent Celery from actually pushing tasks during tests."""
    with patch("src.api.routers.projects.run_project") as mock:
        mock.delay = MagicMock(return_value=None)
        yield mock
