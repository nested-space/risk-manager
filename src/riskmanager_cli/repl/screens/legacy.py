"""Transitional adapter bridging the engine's Screen seam to legacy dispatch.

While the application's per-screen behaviour is migrated out of
:class:`~..commands.CommandDispatcher` into dedicated :class:`AppScreen`
subclasses, screens that have not been extracted yet are served by
:class:`LegacyScreen`. It implements the engine
:class:`~...repl_engine.dispatch.Screen` protocol by routing each call back to
the dispatcher's existing ``_dispatch_<track>`` / ``_hotkey_<track>`` /
``render_screen`` / ``activate_selection`` / ``search_screen`` methods.

This module is scaffolding: as each screen graduates to a real :class:`AppScreen`
the corresponding legacy methods are removed, and once every screen is migrated
this adapter is deleted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...repl_engine import ListItem, ScreenSpec
from ..renderers.library_home_renderer import LIBRARY_HOME_TABS
from .base import AppScreen

if TYPE_CHECKING:
    from ..commands import CommandDispatcher


class LegacyScreen(AppScreen):
    """Route engine Screen calls to the dispatcher's per-track legacy methods."""

    def __init__(self, app: CommandDispatcher, key: str, track: str, spec: ScreenSpec) -> None:
        """Adapt the legacy screen identified by *key*/*track*.

        Args:
            app: The owning dispatcher holding the legacy methods.
            key: The screen-registry key (drives the spec and tab state).
            track: The navigation track whose ``_dispatch_``/``_hotkey_`` handlers
                service this screen.
            spec: The screen's capability descriptor.
        """
        super().__init__(app)
        self.key = key
        self.spec = spec
        self._track = track

    def tab_count(self) -> int:
        """Return the screen's tab count (only the library home is tabbed)."""
        return len(LIBRARY_HOME_TABS) if self.key == "library_home" else 0

    def is_navigable(self) -> bool:
        """Return whether caret navigation applies.

        The Library home's navigation belongs to its ``Libraries`` tab only; the
        ``Information`` tab has no cards, so it reports as non-navigable.
        """
        if self.key == "library_home" and self.app.active_tab() != 0:
            return False
        return self.spec.navigable

    async def render(self) -> list[str]:
        """Render via the dispatcher's legacy per-track renderer."""
        return await self.app.render_screen()

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Forward a command to the legacy ``_dispatch_<track>`` handler."""
        handler = getattr(self.app, f"_dispatch_{self._track}", None)
        if handler is None:
            return None
        result: list[str] | str | None = await handler(verb, args)
        return result

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Forward a hotkey to the legacy ``_hotkey_<track>`` handler."""
        handler = getattr(self.app, f"_hotkey_{self._track}", None)
        if handler is None:
            return None
        result: list[str] | str | None = await handler(key_text)
        return result

    async def activate(self, item: ListItem) -> list[str]:
        """Open the selected item via the legacy activation router."""
        return await self.app.activate_selection(item)

    async def search(self, query: str) -> list[str]:
        """Filter the screen via the legacy search router."""
        return await self.app.search_screen(query)
