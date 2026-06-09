# Persistence Layer

## Overview

The persistence layer adapts the reference PostgreSQL implementation to SQLite
using `aiosqlite` as the async driver. All SQLAlchemy ORM patterns remain
identical — only the connection URL, driver, and column types change.

---

## Driver: `aiosqlite`

```
pip install aiosqlite>=0.19.0
```

`aiosqlite` wraps Python's built-in `sqlite3` module with async/await support.
SQLAlchemy uses it via the `sqlite+aiosqlite://` dialect.

---

## Connection URL

```python
# Format
"sqlite+aiosqlite:///path/to/database.db"

# In-memory (for tests)
"sqlite+aiosqlite:///:memory:"

# Absolute path
"sqlite+aiosqlite:////home/user/.rmgr/riskmanager.db"
```

---

## Engine Configuration

SQLite does **not** support connection pooling in the same way as PostgreSQL.
The engine should be configured without pool settings:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    "sqlite+aiosqlite:///./riskmanager-dev.db",
    echo=False,
    # SQLite-specific settings:
    connect_args={
        "check_same_thread": False,  # Required for async SQLite
        "timeout": 30,               # Wait up to 30s for DB lock
    },
)
```

**No pool settings (`pool_size`, `max_overflow`)** — SQLite is a single-file
database and does not benefit from connection pooling. Concurrent writes are
serialized by the WAL journal.

---

## SQLite PRAGMA Settings

Enable foreign key enforcement and WAL journal mode on every connection.
These must be set per-connection in SQLAlchemy via an event listener:

```python
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(url, connect_args={"check_same_thread": False})

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragmas(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")   # enforce FK constraints
    cursor.execute("PRAGMA journal_mode = WAL")  # enable WAL for better concurrency
    cursor.execute("PRAGMA busy_timeout = 5000") # 5s wait on locked DB
    cursor.close()
```

**Why WAL mode?** Write-Ahead Logging allows concurrent readers during a write
operation, reducing lock contention in a single-user application with rapid
successive operations.

---

## Session Context Manager (`db_session.py`)

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from ..config.settings import Environment, build_db_url


@asynccontextmanager
async def get_db_session(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> AsyncGenerator[AsyncSession, None]:
    """Create an async SQLite session with proper lifecycle management.

    Enables foreign keys and WAL mode on each new connection. Automatically
    rolls back on exception and disposes the engine on exit.

    Args:
        env: Database environment selector (DEV or PROD).
        verbose: If True, prints the database path.

    Yields:
        An AsyncSession with expire_on_commit=False.
    """
    engine = create_async_engine(
        build_db_url(env, verbose),
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = None
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
            except Exception:
                pass
        try:
            await engine.dispose()
        except Exception:
            pass
```

---

## Model Column Types in SQLite

### UUIDs

PostgreSQL uses a native `UUID` type. SQLite stores UUIDs as `TEXT`.

```python
# In model/tables.py
from uuid import uuid4
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Text

class Material(SQLModel, table=True):
    id: Optional[str] = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(Text, primary_key=True),
    )
```

All UUID comparisons use string equality (SQLite `TEXT` column):
```python
Material.id == str(some_uuid)
```

### Timestamps

PostgreSQL uses `DateTime(timezone=True)`. SQLite stores datetimes as text
in ISO 8601 format. SQLAlchemy handles the conversion automatically with
`DATETIME` type.

```python
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime
from sqlmodel import Field

class Material(SQLModel, table=True):
    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime, nullable=False),
    )
```

**Updating `updated_at`:** SQLite has no `ON UPDATE` trigger equivalent.
Update the field explicitly in application code:

```python
material.updated_at = datetime.now(timezone.utc)
session.add(material)
await session.commit()
```

### Enums

Use SQLAlchemy `Enum` with `native_enum=False` so the type is stored as `TEXT`:

```python
from sqlalchemy import Enum as SAEnum
from .enums import TA

therapy_area: TA = Field(
    sa_column=Column(
        SAEnum(TA, native_enum=False),  # TEXT in SQLite, no DB enum type created
        nullable=False,
    )
)
```

### Boolean

SQLite stores booleans as `INTEGER` (0 or 1). SQLAlchemy `Boolean` handles
this automatically:

```python
from sqlalchemy import Boolean

is_isolated: bool = Field(
    sa_column=Column(Boolean, nullable=False, default=False)
)
```

### Numeric (Stoichiometry)

Use SQLAlchemy `Numeric` or Python `float`/`REAL`:

```python
from sqlalchemy import Numeric

stoichiometry: Optional[float] = Field(
    default=None,
    sa_column=Column(Numeric(precision=5, scale=2), nullable=True),
)
```

---

## Database Initialization

On first run (or in development), create all tables from SQLModel metadata:

```python
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine

async def init_db(db_url: str) -> None:
    """Create all tables if they don't exist."""
    engine = create_async_engine(db_url, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await engine.dispose()
```

Call this once at application startup before any CLI operations if running
in greenfield mode without Alembic.

---

## Migration Management with Alembic

For a production application, use **Alembic** for schema migrations rather
than `create_all()`.

### Setup

```bash
pip install alembic
alembic init alembic
```

### `alembic/env.py` (async SQLite)

```python
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from riskmanager_cli.model.tables import SQLModel

config = context.config
target_metadata = SQLModel.metadata

def run_migrations_online():
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        connect_args={"check_same_thread": False},
    )
    # ... standard async Alembic setup
```

### `alembic.ini`

```ini
[alembic]
script_location = alembic
sqlalchemy.url = sqlite+aiosqlite:///./riskmanager-dev.db
```

### Creating a Migration

```bash
alembic revision --autogenerate -m "add manufacturing_process_risk table"
alembic upgrade head
```

### Running Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# View current revision
alembic current

# Downgrade one revision
alembic downgrade -1
```

---

## Testing with In-Memory SQLite

Use `sqlite+aiosqlite:///:memory:` for fast, isolated integration tests:

```python
import pytest
import pytest_asyncio
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
```

---

## SQLite Limitations vs PostgreSQL

| Feature | PostgreSQL | SQLite |
|---------|-----------|--------|
| Concurrent writes | Full multi-writer | Single writer (WAL mode improves reads) |
| UUID type | Native | TEXT |
| ARRAY type | Native | Not available — use alias sub-tables |
| JSONB type | Native | Not available — removed or replaced |
| ENUM type | Native DB type | TEXT via SQLAlchemy |
| DB-level triggers | Full support | Limited; avoid for version/audit tables |
| Full-text search | `tsvector` | FTS5 (different API) |
| Connection pool | Required | Not applicable |
| Schema | Namespaces supported | Single schema only |
| `gen_random_uuid()` | Server function | Python `uuid4()` |

---

## CRUDMixin Pattern (Replacing riskmanager_server wheel)

The reference implementation uses a `CRUDMixin` from the `riskmanager_server` wheel.
In the greenfield, implement this locally in `model/util.py`:

```python
from typing import TypeVar, Type, List, Optional, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class CRUDMixin:
    """Provides get_all, get_where, and update_fields class methods."""

    @classmethod
    async def get_all(cls: Type[T], session: AsyncSession) -> List[T]:
        """Fetch all records of this model type."""
        result = await session.execute(select(cls))
        return list(result.scalars().all())

    @classmethod
    async def get_where(cls: Type[T], session: AsyncSession, condition: Any) -> List[T]:
        """Fetch records matching a SQLAlchemy condition expression."""
        result = await session.execute(select(cls).where(condition))
        return list(result.scalars().all())

    async def update_fields(self, session: AsyncSession, **kwargs) -> None:
        """Update specified fields and commit."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        session.add(self)
        await session.commit()
        await session.refresh(self)
```

Use this mixin in all table models:

```python
class Material(SQLModel, CRUDMixin, table=True):
    __tablename__ = "material"
    ...
```
