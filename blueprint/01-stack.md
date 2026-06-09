# Technology Stack

## Language

- **Python** `>=3.10`
- Uses modern Python features: `match`/`case`, `X | Y` union types, `TypeVar`, `asyncio`

---

## Core Dependencies

### CLI Framework

| Package | Version | Purpose |
|---------|---------|---------|
| `blessed` | `>=1.19.0` | Full-screen terminal control; key input event loop; ANSI cursor/colour management |
| `colorama` | `>=0.4.6` | Cross-platform terminal color support (ANSI escape codes); used in operations layer output |
| `asyncio` | stdlib | Async event loop for database I/O operations |

> **Note:** `argparse` and `argcomplete` are **not used** in the greenfield. All
> command parsing is handled by the REPL's slash-command dispatcher (`repl/commands.py`).

### Data Validation

| Package | Version | Purpose |
|---------|---------|---------|
| `pydantic` | `>=2.0.0` | Create/update schema contracts, enum validation, data parsing |
| `sqlmodel` | `>=0.0.8` | SQLAlchemy + Pydantic integrated ORM for table definitions |

### Database Layer

| Package | Version | Purpose |
|---------|---------|---------|
| `sqlalchemy[asyncio]` | `>=2.0.0` | Async ORM engine, session management, query building |
| `aiosqlite` | `>=0.19.0` | Async SQLite driver (replaces asyncpg from reference implementation) |

### Chemistry

| Package | Version | Purpose |
|---------|---------|---------|
| `rdkit` | `>=2023.3.1` | SMILES validation, canonicalization, molecular structure handling |

### External Services

| Package | Version | Purpose |
|---------|---------|---------|
| `httpx` | `>=0.24.0` | Async HTTP client for DMTA enrichment service calls |

---

## Removed Dependencies (vs reference implementation)

| Removed Package | Reason |
|-----------------|--------|
| `asyncpg` | PostgreSQL async driver — replaced by `aiosqlite` |
| `fastapi` | HTTP server framework — REPL-only, not needed |
| `riskmanager_server` wheel | External wheel with Postgres models — replaced by local `model/` package |
| `argparse` | stdlib argument parser — replaced by REPL command dispatcher |
| `argcomplete` | Tab completion for argparse — removed with argparse |

---

## Development Dependencies (not in production requirements)

| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |
| `ruff` | Fast Python linter and formatter |

---

## `pyproject.toml` (Reference)

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "riskmanager-cli"
version = "0.3.0"
description = "Interactive REPL shell for riskmanager database operations"
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.10"
dependencies = [
    "aiosqlite>=0.19.0",
    "blessed>=1.19.0",
    "colorama>=0.4.6",
    "httpx>=0.24.0",
    "pydantic>=2.0.0",
    "rdkit>=2023.3.1",
    "sqlalchemy[asyncio]>=2.0.0",
    "sqlmodel>=0.0.8",
]

[project.scripts]
riskmanager-cli = "riskmanager_cli.__main__:cli_main"
rmgr = "riskmanager_cli.__main__:cli_main"

[tool.setuptools.packages.find]
where = ["src"]
include = ["riskmanager_cli*"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["asyncio: asyncio mark"]
```

---

## `requirements.txt` (Reference)

```
aiosqlite>=0.19.0
blessed>=1.19.0
colorama>=0.4.6
httpx>=0.24.0
pydantic>=2.0.0
rdkit>=2023.3.1
SQLAlchemy[asyncio]>=2.0.0
sqlmodel>=0.0.8
```

---

## SQLite vs PostgreSQL: Driver Differences

The only driver-level change from the reference implementation is:

| Aspect | PostgreSQL (reference) | SQLite (greenfield) |
|--------|------------------------|---------------------|
| Driver | `asyncpg` | `aiosqlite` |
| Connection URL | `postgresql+asyncpg://user:pwd@host/db` | `sqlite+aiosqlite:///path/to/db.sqlite` |
| Connection pool | `pool_size=5, max_overflow=10` | Not applicable (single-file) |
| UUID generation | `gen_random_uuid()` server function | `uuid.uuid4()` in Python |
| ARRAY columns | Native `ARRAY(Text)` type | JSON TEXT (via `TypeDecorator`) |
| JSONB columns | Native `JSONB` type | JSON TEXT (via `TypeDecorator`) |
| ENUM columns | Native `ENUM` DB type | `TEXT` via SQLAlchemy `Enum` |
| Timestamp TZ | `DateTime(timezone=True)` | `DATETIME` (UTC strings) |

All other SQLAlchemy ORM code (models, sessions, queries) is identical between
the two implementations.
