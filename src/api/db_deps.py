"""FastAPI dependency that yields an async DB session."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: yield an async SQLAlchemy session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
