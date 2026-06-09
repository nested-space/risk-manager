"""
Async database session context manager.

Provides :func:`get_db_session`, the single entry point for obtaining a
:class:`~sqlalchemy.ext.asyncio.AsyncSession` in all operations functions.
Also provides :func:`init_db` for idempotent table creation at startup.

Why this exists:
    All operations functions open their own sessions rather than sharing a
    long-lived session. This module provides the context manager that each
    operation uses, keeping session lifecycle management consistent and
    avoiding session leaks.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import SQLModel

from ..config.settings import Environment, build_db_url
from .connection import build_engine


@asynccontextmanager
async def get_db_session(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> AsyncGenerator[AsyncSession, None]:
    """Create an async SQLite session with full lifecycle management.

    Opens an engine, applies PRAGMA settings via the connect event listener in
    :func:`~.connection.build_engine`, yields the session, rolls back on
    exception, and disposes the engine on exit.

    Each call creates a new engine and session. Sessions are never shared
    between operations.

    Args:
        env: Database environment selector (``DEV`` or ``PROD``).
        verbose: If ``True``, prints the resolved database path.

    Yields:
        An :class:`~sqlalchemy.ext.asyncio.AsyncSession` with
        ``expire_on_commit=False``.

    Raises:
        Any exception raised by the calling code is re-raised after rollback.
    """
    engine = build_engine(build_db_url(env, verbose))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session: AsyncSession | None = None
    try:
        session = session_factory()
        yield session
    except Exception:
        if session:
            await session.rollback()
        raise
    finally:
        if session:
            try:
                await session.close()
            except Exception:  # pylint: disable=broad-except  # best-effort close
                pass
        try:
            await engine.dispose()
        except Exception:  # pylint: disable=broad-except  # best-effort dispose
            pass


async def init_db(db_url: str) -> None:
    """Create all SQLModel tables if they do not already exist.

    Idempotent — safe to call on every application startup. Uses
    ``SQLModel.metadata.create_all`` which issues ``CREATE TABLE IF NOT EXISTS``
    for each registered table class.

    Args:
        db_url: A ``sqlite+aiosqlite://`` connection URL string.
    """
    engine = build_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await engine.dispose()
