"""
SQLite engine factory with PRAGMA configuration.

Provides :func:`create_engine` with the SQLite-specific settings required by
the application: WAL journal mode, foreign key enforcement, and a busy timeout.

Why this exists:
    SQLite PRAGMA settings must be applied per-connection via a SQLAlchemy
    event listener. Centralising engine creation here ensures that every
    engine — whether created by ``db_session.py`` or by ``init_db`` at startup
    — applies the same PRAGMA configuration.
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def build_engine(db_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create an async SQLAlchemy engine configured for SQLite.

    Attaches a connection event listener that enables foreign key enforcement,
    WAL journal mode, and a 5-second busy timeout on every new connection.

    Args:
        db_url: A ``sqlite+aiosqlite://`` connection URL string.
        echo: If ``True``, SQLAlchemy logs all SQL statements. Default ``False``.

    Returns:
        A configured :class:`~sqlalchemy.ext.asyncio.AsyncEngine` instance.
    """
    engine = create_async_engine(
        db_url,
        echo=echo,
        connect_args={
            "check_same_thread": False,  # required for async SQLite usage
            "timeout": 30,
        },
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn: Any, _connection_record: Any) -> None:
        """Apply SQLite PRAGMA settings on every new connection.

        Why this exists:
            PRAGMA settings are per-connection in SQLite. Using a connect-event
            listener is the only reliable way to ensure they are applied for
            every connection that SQLAlchemy creates.
        """
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    return engine
