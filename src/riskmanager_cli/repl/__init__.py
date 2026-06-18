"""Public exports for the riskmanager-cli application REPL layer.

The event loop itself lives in the application-agnostic :mod:`riskmanager_cli.repl_engine`
package; it is re-exported here for convenience so callers can launch the REPL
from the application package.
"""

from __future__ import annotations

from ..repl_engine.loop import start_repl

__all__ = ["start_repl"]
