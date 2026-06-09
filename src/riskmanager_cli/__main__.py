"""Entry point for the riskmanager-cli interactive REPL shell.

Invoke with::

    rmgr
    # or
    riskmanager-cli
    # or
    python -m riskmanager_cli

Startup sequence:

1. Read environment variables (``APP_ENV``, ``APP_DB_PATH``, etc.)
2. Initialise the SQLite database (create tables if absent)
3. Load session state from disk (silently resets on corrupt JSON)
4. Create a :class:`blessed.Terminal` instance
5. Create a :class:`~riskmanager_cli.repl.context.ContextManager` and
   :class:`~riskmanager_cli.repl.screen.ScreenManager`
6. Call :func:`~riskmanager_cli.repl.loop.start_repl` to enter the event loop
"""

from __future__ import annotations

import atexit
import os
import sys
import traceback

import blessed

from .config.settings import Environment, build_db_url
from .database.db_session import init_db
from .repl.commands import CommandDispatcher
from .repl.context import ContextManager
from .repl.loop import start_repl
from .repl.screen import ScreenManager
from .repl.session_state import SessionState


def _resolve_env() -> Environment:
    """Read ``APP_ENV`` and return the matching :class:`~config.settings.Environment`.

    Defaults to :attr:`~config.settings.Environment.DEV` for unknown values.

    Returns:
        The active :class:`~config.settings.Environment`.
    """
    raw = os.getenv("APP_ENV", "dev").strip().lower()
    if raw == "prod":
        return Environment.PROD
    return Environment.DEV


def _register_atexit_cleanup(term: blessed.Terminal) -> None:
    """Register an ``atexit`` handler that restores the terminal on crash.

    The handler is a best-effort safety net. On a clean exit the REPL loop
    itself restores terminal state before returning, so the ``atexit`` handler
    is effectively a no-op in the happy path.

    Args:
        term: The :class:`blessed.Terminal` whose state must be restored.
    """

    def _cleanup() -> None:
        try:
            sys.stdout.write(term.normal_cursor)
            sys.stdout.write(term.exit_fullscreen)
            sys.stdout.write(term.normal)
            sys.stdout.flush()
        except Exception:  # pylint: disable=broad-except  # atexit must never propagate
            pass

    atexit.register(_cleanup)


def cli_main() -> None:
    """Main entry point for the riskmanager-cli REPL.

    Reads environment, initialises the database, loads session state,
    and starts the interactive terminal loop. Handles ``KeyboardInterrupt``
    (Ctrl+C) and ``EOFError`` (Ctrl+D) with session state saved and exit
    code conventions honoured.

    Exit codes:
    - ``0`` — clean exit (``/quit``, Ctrl+D)
    - ``1`` — unhandled exception
    - ``130`` — ``SIGINT`` / Ctrl+C convention
    """
    env = _resolve_env()

    import asyncio  # pylint: disable=import-outside-toplevel

    try:
        asyncio.run(init_db(build_db_url(env)))
    except Exception as exc:  # pylint: disable=broad-except  # startup must report clearly
        sys.stderr.write(f"riskmanager-cli: database initialisation failed: {exc}\n")
        sys.exit(1)

    session = SessionState.load()
    term = blessed.Terminal()
    _register_atexit_cleanup(term)

    ctx = ContextManager()
    screen = ScreenManager(term, ctx)
    dispatcher = CommandDispatcher(ctx, session, screen, env)

    exit_code = 0
    try:
        with term.fullscreen(), term.cbreak(), term.hidden_cursor():
            start_repl(term, ctx, session, screen, dispatcher, env)
    except KeyboardInterrupt:
        exit_code = 130
    except EOFError:
        exit_code = 0
    except Exception:  # pylint: disable=broad-except  # crash handler: always restore terminal
        sys.stderr.write("\n\nriskmanager-cli crashed:\n")
        traceback.print_exc()
        exit_code = 1
    finally:
        try:
            session.save()
        except Exception:  # pylint: disable=broad-except  # save is best-effort on exit
            pass

    sys.exit(exit_code)


if __name__ == "__main__":
    cli_main()
