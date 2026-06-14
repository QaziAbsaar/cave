"""Checkpoint save/load — exact implementation from CLAUDE.md.

Uses asyncpg for direct PostgreSQL access. The `db` parameter is an
asyncpg Connection, matching the canonical CLAUDE.md signature.
"""

import os
from typing import Optional

import asyncpg

from src.orchestrator.state import ProjectState

CHECKPOINT_DB_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://cave:cave_dev@localhost:5432/cave",
)

# asyncpg requires the scheme to be "postgresql://" not "postgresql+asyncpg://"
_DSN: str = CHECKPOINT_DB_URL.replace("+asyncpg", "")


async def get_connection() -> asyncpg.Connection:
    """Open a direct asyncpg connection for checkpoint operations."""
    return await asyncpg.connect(dsn=_DSN)


async def save_checkpoint(state: ProjectState, db: asyncpg.Connection) -> None:
    """Save a full state snapshot to the project_checkpoints table.

    Implements Rule 1–4 from CLAUDE.md:
    - Increment version on every save
    - Serialize full ProjectState as JSONB
    - Use optimistic locking via ON CONFLICT DO NOTHING

    Args:
        state: The current pipeline state (will have version incremented).
        db: An open asyncpg connection.
    """
    state.version += 1
    await db.execute(
        """
        INSERT INTO project_checkpoints (project_id, version, state, agent, status)
        VALUES ($1, $2, $3::jsonb, $4, $5)
        ON CONFLICT (project_id, version) DO NOTHING
        """,
        state.project_id,
        state.version,
        state.model_dump_json(),
        state.current_agent,
        state.status.value,
    )


async def load_latest_checkpoint(project_id: str, db: asyncpg.Connection) -> Optional[ProjectState]:
    """Load the latest checkpoint for a project.

    Args:
        project_id: UUID string identifying the project.
        db: An open asyncpg connection.

    Returns:
        The latest ProjectState, or None if no checkpoint exists.
    """
    row = await db.fetchrow(
        """
        SELECT state FROM project_checkpoints
        WHERE project_id = $1
        ORDER BY version DESC LIMIT 1
        """,
        project_id,
    )
    if row is None:
        return None
    return ProjectState.model_validate_json(row["state"])
