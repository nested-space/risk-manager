"""Shared behaviour for the focused stage/component screens.

Both focus screens confirm-and-delete a single section row. :class:`FocusScreen`
provides that shared helper so the stage and component screens don't duplicate it.
"""

from __future__ import annotations

from collections.abc import Awaitable

from .base import AppScreen


class FocusScreen(AppScreen):
    """Base for the stage- and component-focus screens."""

    async def _unassign_with_notice(self, delete_coro: Awaitable[bool], success: str) -> list[str]:
        """Await a delete operation, then refresh the screen with a status notice."""
        ok = await delete_coro
        if not ok:
            return await self.app.refresh_with_notice("Unassign failed.", "error")
        return await self.app.refresh_with_notice(success)
