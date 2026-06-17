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


def _default_db_path(env: Environment) -> str:
    """Return the default on-disk SQLite path for *env* under ``~/.rmgr/database``.

    Args:
        env: Target environment; selects the production or development filename.

    Returns:
        Absolute path string to the default database file.
    """
    name = "riskmanager.db" if env is Environment.PROD else "riskmanager-dev.db"
    return str(Path.home() / ".rmgr" / "database" / name)


def _resolve_db_path(env: Environment) -> str:
    """Resolve the configured SQLite path string, applying env-var precedence.

    Precedence (the default in cases 2 and 3 lives under ``~/.rmgr/database``):
        1. ``APP_DB_PATH`` (if set) — used regardless of *env*
        2. *env* == ``PROD`` → ``APP_PROD_DB_PATH`` else default
        3. *env* == ``DEV`` (default) → ``APP_DEV_DB_PATH`` else default

    Args:
        env: Target environment.

    Returns:
        The raw database path string (may be ``:memory:`` or contain ``~``).
    """
    override = os.getenv("APP_DB_PATH")
    if override:
        return override
    if env is Environment.PROD:
        return os.getenv("APP_PROD_DB_PATH", _default_db_path(env))
    return os.getenv("APP_DEV_DB_PATH", _default_db_path(env))


def build_db_url(env: Environment, verbose: bool = False) -> str:
    """Build a SQLite async connection URL for the specified environment.

    Connection URL format: ``sqlite+aiosqlite:///path/to/database.db``. The
    default location is ``~/.rmgr/database`` (overridable via the ``APP_DB_PATH``
    / ``APP_PROD_DB_PATH`` / ``APP_DEV_DB_PATH`` environment variables). The
    parent directory of a file-based path is created so SQLite can open it.

    Args:
        env: Target environment.
        verbose: If ``True``, prints the resolved database path to stdout.

    Returns:
        A ``sqlite+aiosqlite://`` connection URL string.
    """
    db_path = _resolve_db_path(env)

    if db_path != ":memory:" and db_path.strip():
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"Database: {db_path} ({env.value})")

    return f"sqlite+aiosqlite:///{db_path}"


def get_db_path(env: Environment) -> Path | None:
    """Resolve the SQLite database file path for *env*, or ``None`` if in-memory.

    Applies the same precedence as :func:`build_db_url` (``APP_DB_PATH`` →
    ``APP_PROD_DB_PATH`` → ``APP_DEV_DB_PATH``) but returns the bare filesystem
    path rather than a connection URL.

    Why this exists:
        First-run seeding must decide whether a database already exists before
        :func:`~..database.db_session.init_db` creates it. That decision needs
        the resolved file path, not the connection URL.

    Args:
        env: Target environment.

    Returns:
        The resolved :class:`pathlib.Path`, or ``None`` for an in-memory
        database (``:memory:``), which has no file and is never seeded.
    """
    raw = _resolve_db_path(env)
    if raw == ":memory:" or not raw.strip():
        return None
    return Path(raw).expanduser()


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


def get_structure_cache_dir() -> Path:
    """Return the directory caching rendered molecular-structure images.

    Respects the ``RMGR_STRUCTURE_CACHE_DIR`` environment variable. Defaults to
    ``~/.rmgr/structures``. The directory is created if it does not exist.

    Returns:
        Resolved :class:`pathlib.Path` for the structure-image cache directory.
    """
    raw = os.getenv("RMGR_STRUCTURE_CACHE_DIR", str(Path.home() / ".rmgr" / "structures"))
    path = Path(raw).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
