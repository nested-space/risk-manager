"""Per-screen behaviour for the risk-manager REPL.

Each module implements one :class:`~...repl_engine.dispatch.Screen`: its
rendering, slash commands, hotkeys, list activation, and search. The dispatcher
maps the current navigation context to one of these screens; screens not yet
extracted from :class:`~..commands.CommandDispatcher` are served by
:class:`~.legacy.LegacyScreen`.
"""

from __future__ import annotations

from .base import AppScreen
from .legacy import LegacyScreen

__all__ = ["AppScreen", "LegacyScreen"]
