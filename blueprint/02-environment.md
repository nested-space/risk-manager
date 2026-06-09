# Environment Variables and Configuration

## Overview

The application selects a SQLite database file based on the current environment
and reads all configuration from environment variables at startup. No config files
are required for basic usage — the defaults work out of the box.

Session state (recently visited projects, last-used route, etc.) is persisted to
a JSON file and is separate from the database.

---

## Environment Variables

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `dev` | Active environment. Accepted values: `dev`, `prod` |
| `APP_DEV_DB_PATH` | `./governance-dev.db` | Path to the SQLite file used in `dev` environment |
| `APP_PROD_DB_PATH` | `./governance.db` | Path to the SQLite file used in `prod` environment |
| `APP_DB_PATH` | _(none)_ | If set, overrides both `APP_DEV_DB_PATH` and `APP_PROD_DB_PATH` regardless of `APP_ENV` |

**Precedence:**
1. `APP_DB_PATH` (if set) → always used, ignores `APP_ENV`
2. `APP_ENV=prod` → uses `APP_PROD_DB_PATH`
3. `APP_ENV=dev` (default) → uses `APP_DEV_DB_PATH`

### Session State Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GCLI_SESSION_PATH` | `~/.gcli/session.json` | Path to the JSON session state file |

The session state file stores:
- Recent projects (last 5 visited, in order of last use)
- Recent routes per project (last N used per project)
- Last active context (track, project ID, process ID)

This file is created automatically on first run. If it is missing or corrupt,
the application starts fresh at the home screen without error.

### DMTA Enrichment (Optional)

These variables are only required if DMTA enrichment is enabled (via `/add material
--enable-dmta` or the session setting). DMTA enrichment automatically fetches SMILES
and synonyms for materials from an external chemical database service.

| Variable | Default | Description |
|----------|---------|-------------|
| `DMTA_API_URL` | _(none)_ | Base URL of the DMTA enrichment service |
| `DMTA_API_KEY` | _(none)_ | API key for authenticating with the DMTA service |

If `DMTA_API_URL` is not set and DMTA enrichment is requested, the application prints
a warning and skips enrichment rather than failing.

---

## Settings Module

The `config/settings.py` module provides:

```python
import os
from enum import Enum
from pathlib import Path

class Environment(str, Enum):
    """Database environment selector."""
    DEV = "dev"
    PROD = "prod"


def build_db_url(env: Environment, verbose: bool = False) -> str:
    """Build a SQLite connection URL for the specified environment.

    Connection URL format: sqlite+aiosqlite:///path/to/database.db

    Precedence:
        1. APP_DB_PATH (if set) — used regardless of env
        2. env=PROD → APP_PROD_DB_PATH
        3. env=DEV → APP_DEV_DB_PATH

    Args:
        env: Target environment.
        verbose: If True, prints the resolved database path.

    Returns:
        A sqlite+aiosqlite connection URL string.
    """
    override = os.getenv("APP_DB_PATH")
    if override:
        db_path = override
    elif env is Environment.PROD:
        db_path = os.getenv("APP_PROD_DB_PATH", "./governance.db")
    else:
        db_path = os.getenv("APP_DEV_DB_PATH", "./governance-dev.db")

    if verbose:
        print_key_value("Database", f"{db_path} ({env.value})")

    return f"sqlite+aiosqlite:///{db_path}"


def get_session_path() -> Path:
    """Return the path to the JSON session state file.

    Respects the GCLI_SESSION_PATH environment variable. Defaults to
    ~/.gcli/session.json. The parent directory is created if it does not exist.

    Returns:
        Resolved Path object for the session state file.
    """
    raw = os.getenv("GCLI_SESSION_PATH", str(Path.home() / ".gcli" / "session.json"))
    path = Path(raw).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
```

---

## Recommended Shell Setup

Add to `~/.zshrc` or `~/.bashrc`:

```bash
# Default to dev environment
export APP_ENV=dev
export APP_DEV_DB_PATH="$HOME/.gcli/governance-dev.db"
export APP_PROD_DB_PATH="$HOME/.gcli/governance.db"

# Optional: override session state file location
# export GCLI_SESSION_PATH="$HOME/.gcli/session.json"

# Optional: DMTA enrichment
# export DMTA_API_URL="https://dmta.example.com/api"
# export DMTA_API_KEY="your-api-key-here"
```

Create the data directory:

```bash
mkdir -p ~/.gcli
```

---

## Database Initialization

The SQLite database file is created automatically on first use if it does not
exist. Tables are created via SQLAlchemy's `create_all()` on startup (or via
Alembic migrations — see `10-persistence-layer.md` for details).

---

## Differences from Reference Implementation

| Reference Variable | Greenfield Equivalent | Notes |
|--------------------|-----------------------|-------|
| `GOVERNANCE_DB_USER` | _(not needed)_ | SQLite has no user auth |
| `GOVERNANCE_DB_PASSWORD` | _(not needed)_ | SQLite has no password |
| `GOVERNANCE_DB_HOST` | _(not needed)_ | SQLite is file-based |
| `GOVERNANCE_DB_PORT` | _(not needed)_ | SQLite has no port |
| `GOVERNANCE_DB_NAME` | `APP_PROD_DB_PATH` | Path to SQLite file |
| `GOVERNANCE_DB_TEST_NAME` | `APP_DEV_DB_PATH` | Path to dev SQLite file |
| `--env dev\|prod` CLI flag | `APP_ENV` env var | No CLI flag; set once in shell profile |
