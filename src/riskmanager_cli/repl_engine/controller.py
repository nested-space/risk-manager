"""The contract the event loop drives to render and mutate application state.

:class:`ReplController` is the seam between the application-agnostic engine and
the concrete application. The :func:`~.loop.start_repl` loop depends only on this
protocol; the application's command dispatcher implements it. This inversion is
what keeps the engine free of any domain knowledge — it never imports the
application, only this abstraction.

All screen-producing methods return display lines (``list[str]``); some also
accept a bare ``str`` for single-line results. Header text, capability flags, and
navigation are surfaced as plain values so the loop never inspects domain state.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .forms import PickerState, PromptState
from .list_navigator import ListItem, ListNavigator


@runtime_checkable
class ReplController(Protocol):  # pylint: disable=too-many-public-methods  # the loop's full drive surface
    """Application-facing contract for driving the REPL event loop."""

    # --- lifecycle & global state ---

    @property
    def quit_requested(self) -> bool:
        """Whether the application has asked the loop to exit."""

    def header(self) -> tuple[str, str]:
        """Return the status-bar header as ``(left, right)`` text."""

    async def render_current(self) -> list[str]:
        """Return the current screen's display lines."""

    def take_notice(self) -> tuple[str, str] | None:
        """Return and clear the pending ``(message, level)`` status notice."""

    def command_hints(self) -> str:
        """Return the info-line action legend for the current screen."""

    def help_legend(self) -> list[str]:
        """Return the full control legend for the current screen (``?``)."""

    def start_quit_confirm(self) -> list[str]:
        """Open the quit-confirmation modal and return its lines."""

    # --- screen capabilities ---

    def is_navigable(self) -> bool:
        """Whether ``↑↓``/``Enter`` list navigation applies to this screen."""

    def supports_search(self) -> bool:
        """Whether incremental ``/`` search applies to this screen."""

    def tab_hint(self) -> str | None:
        """Return the tab grammar hint for a tabbed screen, else ``None``."""

    def tab_count(self) -> int:
        """Return the number of tabs on the current screen (0 when untabbed)."""

    # --- navigation ---

    @property
    def list_navigator(self) -> ListNavigator | None:
        """The active list navigator, or ``None`` when the screen has no list."""

    async def activate_list_selection(self, item: ListItem) -> list[str]:
        """Open the selected list *item* and return the resulting screen."""

    def cycle_active_tab(self, step: int) -> None:
        """Advance the active tab by *step* (wrapping)."""

    async def pop_context(self) -> list[str] | None:
        """Pop one navigation level, or return ``None`` at the root."""

    # --- command line & search ---

    async def dispatch(self, command: str) -> list[str] | str:
        """Execute a ``:`` command line and return the resulting screen."""

    async def search(self, query: str) -> list[str]:
        """Return the current screen filtered by an incremental ``/`` *query*."""

    async def handle_hotkey(self, key_text: str) -> list[str] | str | None:
        """Handle a Ctrl-<letter> hotkey; ``None`` when it is unhandled."""

    # --- modal: guided prompt ---

    @property
    def prompt_state(self) -> PromptState | None:
        """The active guided-prompt state, or ``None``."""

    def prompt_prefill(self) -> str:
        """Return the editable initial text for the active prompt field."""

    async def advance_prompt(self, value: str) -> list[str]:
        """Submit *value* to the active guided prompt."""

    def prompt_move(self, direction: str) -> list[str]:
        """Move the active select field's highlight ``"up"`` or ``"down"``."""

    async def submit_prompt_selection(self) -> list[str]:
        """Submit the highlighted option of the active select field."""

    async def cancel_prompt(self) -> list[str]:
        """Cancel the active guided prompt and restore the current screen."""

    # --- modal: typeahead picker ---

    @property
    def picker_state(self) -> PickerState | None:
        """The active typeahead-picker state, or ``None``."""

    def update_picker_query(self, query: str) -> list[str]:
        """Re-filter the active picker for *query*."""

    def picker_move(self, direction: str) -> list[str]:
        """Move the picker highlight ``"up"`` or ``"down"``."""

    async def picker_select(self) -> list[str]:
        """Choose the highlighted match and invoke the picker callback."""

    async def cancel_picker(self) -> list[str]:
        """Cancel the active typeahead picker and restore the current screen."""
