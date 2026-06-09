"""Shared pytest fixtures for riskmanager-cli tests."""

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.database.db_session import init_db


@pytest.fixture
def mock_session() -> AsyncMock:
    """Async mock session for unit tests (no database required)."""
    session = AsyncMock(spec=AsyncSession)
    session.get_where = AsyncMock(return_value=[])
    session.get_all = AsyncMock(return_value=[])
    return session


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Real in-memory SQLite session for low-level integration tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def temp_env(tmp_path: Path) -> Environment:
    """DEV environment backed by a fresh temporary SQLite file.

    Why this exists:
        Operations functions create their own sessions via ``get_db_session(env)``.
        This fixture points ``APP_DB_PATH`` at a temp file so each test runs
        against an isolated, pre-initialised schema without touching the real DB.
    """
    db_path = tmp_path / "test.db"
    os.environ["APP_DB_PATH"] = str(db_path)
    await init_db(f"sqlite+aiosqlite:///{db_path}")
    yield Environment.DEV
    os.environ.pop("APP_DB_PATH", None)
