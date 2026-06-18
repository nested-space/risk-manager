"""Per-screen behaviour for the risk-manager REPL.

Each module implements one :class:`~...repl_engine.dispatch.Screen`: its
rendering, slash commands, hotkeys, list activation, and search. The dispatcher
(:class:`~..commands.CommandDispatcher`) maps the current navigation context to
one of these screens.
"""

from __future__ import annotations

from .base import AppScreen

__all__ = ["AppScreen"]
