"""
Application configuration: environment selection and database URL construction.

Reads all configuration from environment variables at startup. No config files
are required — the defaults work out of the box for local development.

Why this exists:
    Centralises all environment-variable reads into one place so that every
    other module imports ``Environment`` and ``build_db_url`` rather than
    calling ``os.getenv`` directly. This makes the configuration surface
    explicit and easy to test.
"""

import os
from enum import Enum
from pathlib import Path


class Environment(str, Enum):
    """Database environment selector.

    Attributes:
        DEV: Development environment; uses ``APP_DEV_DB_PATH``.
        PROD: Production environment; uses ``APP_PROD_DB_PATH``.
    """

    DEV = "dev"
    PROD = "prod"


def build_db_url(env: Environment, verbose: bool = False) -> str:
    """Build a SQLite async connection URL for the specified environment.

    Connection URL format: ``sqlite+aiosqlite:///path/to/database.db``

    Precedence:
        1. ``APP_DB_PATH`` (if set) — used regardless of *env*
        2. *env* == ``PROD`` → ``APP_PROD_DB_PATH``
        3. *env* == ``DEV`` (default) → ``APP_DEV_DB_PATH``

    Args:
        env: Target environment.
        verbose: If ``True``, prints the resolved database path to stdout.

    Returns:
        A ``sqlite+aiosqlite://`` connection URL string.
    """
    override = os.getenv("APP_DB_PATH")
    if override:
        db_path = override
    elif env is Environment.PROD:
        db_path = os.getenv("APP_PROD_DB_PATH", "./riskmanager.db")
    else:
        db_path = os.getenv("APP_DEV_DB_PATH", "./riskmanager-dev.db")

    if verbose:
        print(f"Database: {db_path} ({env.value})")

    return f"sqlite+aiosqlite:///{db_path}"


def get_session_path() -> Path:
    """Return the path to the JSON session state file.

    Respects the ``RMGR_SESSION_PATH`` environment variable. Defaults to
    ``~/.rmgr/session.json``. The parent directory is created if it does not
    exist.

    Returns:
        Resolved :class:`pathlib.Path` for the session state file.
    """
    raw = os.getenv("RMGR_SESSION_PATH", str(Path.home() / ".rmgr" / "session.json"))
    path = Path(raw).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
