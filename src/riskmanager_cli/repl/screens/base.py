"""Base class for application screens driven by the engine's ScreenRouter.

Each screen of the risk-manager REPL is a :class:`~..repl_engine.dispatch.Screen`
implementation. :class:`AppScreen` supplies sensible defaults for the protocol so
concrete screens only override the interaction surface they actually offer. Every
screen holds a reference to the owning :class:`~..commands.CommandDispatcher`,
which is the shared application state (navigation context, session, screen
manager, modal controller) the screens collaborate through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...repl_engine import ListItem, ListNavigator, ScreenSpec
from ...service.structure_viewer import StructureResult, show_structure

if TYPE_CHECKING:
    from ..commands import CommandDispatcher

#: Capability fallback for a screen that declares no spec of its own.
_DEFAULT_SPEC = ScreenSpec(False, False, ())


class AppScreen:
    """Default :class:`~..repl_engine.dispatch.Screen` behaviour for the app.

    Concrete screens set :attr:`key` and :attr:`spec` and override the
    interaction methods (``render``/``run_command``/``run_hotkey``/``activate``/
    ``search``) they support; the rest fall back to no-op defaults here.
    """

    key: str = ""
    spec: ScreenSpec = _DEFAULT_SPEC

    def __init__(self, app: CommandDispatcher) -> None:
        """Bind the screen to the shared application dispatcher.

        Args:
            app: The owning dispatcher, used for shared navigation/session state.
        """
        self.app = app

    @property
    def list_navigator(self) -> ListNavigator | None:
        """Return the shared list navigator (one per REPL, on the dispatcher)."""
        return self.app.navigator

    def is_navigable(self) -> bool:
        """Return whether caret navigation applies (defaults to the spec)."""
        return self.spec.navigable

    def tab_count(self) -> int:
        """Return the number of tabs (untabbed by default)."""
        return 0

    async def render(self) -> list[str]:
        """Render the screen (no content by default)."""
        return []

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Handle a slash command (unhandled by default)."""
        del verb, args
        return None

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Handle a Ctrl-<letter> hotkey (unhandled by default)."""
        del key_text
        return None

    async def activate(self, item: ListItem) -> list[str]:
        """Open the selected list item (re-renders the screen by default)."""
        del item
        return await self.app.render_current()

    async def search(self, query: str) -> list[str]:
        """Filter the screen by an incremental query (re-renders by default)."""
        del query
        return await self.app.render_current()

    async def show_structure_notice(self, name: str, smiles: str | None) -> list[str]:
        """Render *smiles* to an image and open it, returning a status notice.

        Shared ``^K`` behaviour for every screen that shows a molecule: maps each
        :class:`~...service.structure_viewer.StructureResult` to a notice so every
        path (missing SMILES, render failure, no viewer, launch failure) is
        reported on the input row.

        Args:
            name: Human-readable label for the molecule, used in the notice.
            smiles: The molecule's SMILES, or ``None`` when it has none.

        Returns:
            The re-rendered screen lines, with the outcome surfaced as a notice.
        """
        if not smiles:
            return await self.app.refresh_with_notice(
                f"No SMILES available for '{name}'.", "warning"
            )
        match show_structure(str(smiles)):
            case StructureResult.OK:
                return await self.app.refresh_with_notice(f"Opened structure for '{name}'.")
            case StructureResult.RENDER_FAILED:
                return await self.app.refresh_with_notice(
                    "Could not render structure (invalid SMILES).", "error"
                )
            case StructureResult.NO_VIEWER:
                return await self.app.refresh_with_notice(
                    "No image viewer found (install feh).", "error"
                )
            case _:
                return await self.app.refresh_with_notice("Failed to open image viewer.", "error")
