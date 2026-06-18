"""The landing screen: three top-level track cards (projects, library, admin)."""

from __future__ import annotations

from ...repl_engine import ListItem
from ..hotkeys import CTRL_B, CTRL_N, CTRL_P
from ..renderers.home_renderer import CARDS as HOME_CARDS
from ..renderers.home_renderer import render_home
from .base import AppScreen
from .specs import SCREEN_SPECS


class HomeScreen(AppScreen):
    """The REPL landing screen.

    The three tracks reachable from here — the project picker, the library, and
    admin — are shown as a fixed three-item navigator (matching
    :data:`~..renderers.home_renderer.CARDS`) so arrow keys and Enter select a
    track exactly like any other list screen, and ``^P``/``^B``/``^N`` jump to
    them directly. Entering a track is delegated to the dispatcher, which owns the
    navigation context.
    """

    key = "home"
    spec = SCREEN_SPECS["home"]

    async def render(self) -> list[str]:
        """Render the banner and the three track cards."""
        items = [ListItem(label=title, item_id=key) for key, title, _hotkey in HOME_CARDS]
        navigator = self.app.rebuild_navigator([], items)
        return render_home(
            navigator.selected_index,
            width=self.app.screen.width,
            height=self.app.screen.output_height,
            bold=self.app.screen.bold,
        )

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Open the project picker or the library from the landing screen."""
        if verb == "/project":
            return await self.app.enter_project_select()
        if verb == "/library":
            sub_mode = args[0].lower() if args else "select"
            if sub_mode not in {"materials", "ncrm", "counterions", "select"}:
                return ["Usage: /library [materials|ncrm|counterions]"]
            return await self.app.enter_library(sub_mode)
        return None

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Jump to projects (``^P``), the library (``^B``), or admin (``^N``)."""
        if key_text == CTRL_P:
            return await self.app.enter_project_select()
        if key_text == CTRL_B:
            return await self.app.enter_library("select")
        if key_text == CTRL_N:
            return self.app.enter_admin()
        return None

    async def activate(self, item: ListItem) -> list[str]:
        """Open the selected track card."""
        if item.item_id == "project":
            return await self.app.enter_project_select()
        if item.item_id == "library":
            return await self.app.enter_library("select")
        if item.item_id == "admin":
            return self.app.enter_admin()
        return await self.app.render_current()
