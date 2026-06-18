"""Generic screen dispatch for a blessed-based REPL.

This module is application-agnostic: it knows nothing about any domain, command
vocabulary, or navigation model. It provides the reusable machinery an
application composes to drive the event loop:

* :class:`ScreenSpec` — a per-screen capability/hint descriptor.
* :func:`screen_controls` — derive a screen's full control legend from its spec.
* :func:`parse_command` — tokenise a raw command line into verb + arguments.
* :class:`TabState` — hold the active tab index for the current tabbed screen.
* :class:`Screen` — the protocol one screen of behaviour implements.
* :class:`ScreenRouter` — a base implementing the generic slice of
  :class:`~.controller.ReplController` by delegating to the active screen.

An application supplies one :class:`Screen` per screen and subclasses
:class:`ScreenRouter`, implementing :meth:`ScreenRouter.active_screen` to map its
own navigation state onto a screen. The engine never learns the application's
navigation vocabulary — it sees only opaque screen keys and :class:`Screen`
objects, so the same router drives any blessed-based TUI.
"""

from __future__ import annotations

import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .forms import ModalController, PickerState, PromptState
from .list_navigator import ListItem, ListNavigator
from .screen import ScreenManager

#: Sentinel a command or hotkey returns to ask the event loop to exit.
QUIT = "__QUIT__"


@dataclass(frozen=True)
class ScreenSpec:
    """Capability and hint descriptor for one REPL screen.

    The single source of truth for what a screen offers. The two footer lines
    derive their contents from it, with a strict division of responsibility:

    * **Nav-hint line** = *interaction grammar*. Built from :attr:`navigable`
      (``↑↓ navigate · Enter select``) and :attr:`searchable` (``/ search``), plus
      the always-present ``: command`` and ``? help``.
    * **Info line** = *screen actions*. Built from :attr:`actions` (Ctrl-hotkeys)
      plus :attr:`back`.

    The two lines never share a token: movement and global modes belong to the
    nav line, entity actions to the info line. ``actions`` therefore lists ONLY
    Ctrl-<letter> hotkeys, each of which the screen's hotkey handler must service.

    Attributes:
        navigable: Whether ``↑↓``/``Enter`` caret navigation applies (also drives
            the PgUp/PgDn caret-paging behaviour in the loop).
        searchable: Whether incremental "/" search applies.
        actions: Info-line Ctrl-hotkey entries, e.g. ``("^A add", "^E edit")``.
        back: Trailing info-line entry (``"^C back"`` or ``"^C quit"``).
        tab_hint: Nav-line grammar hint for a tabbed screen (e.g. ``"Tab switch
            tabs"``), or ``None`` when the screen has no tabs.
    """

    navigable: bool
    searchable: bool
    actions: tuple[str, ...]
    back: str = "^C back"
    tab_hint: str | None = None


def screen_controls(spec: ScreenSpec) -> list[str]:
    """Return the complete control list for *spec* (grammar + actions).

    Used by the ``?`` legend, which — unlike the footer — shows everything in one
    place. The interaction grammar comes first, then the screen's action hotkeys
    and its back entry.
    """
    grammar: list[str] = []
    if spec.navigable:
        grammar += ["↑↓ navigate", "Enter select"]
    if spec.searchable:
        grammar.append("/ search")
    if spec.tab_hint:
        grammar.append(spec.tab_hint)
    grammar += [": command", "? help"]
    return [*grammar, *spec.actions, spec.back]


@dataclass(frozen=True)
class ParsedCommand:
    """A parsed slash command: its lowercased *verb* and remaining *args*."""

    verb: str
    args: list[str]


def parse_command(line: str) -> ParsedCommand | list[str] | None:
    """Tokenise a raw command line.

    Args:
        line: Raw user-entered command text.

    Returns:
        ``None`` when *line* is blank (the caller should re-render the current
        screen); a ``list[str]`` of message lines for a non-command input or a
        tokenisation error; otherwise a :class:`ParsedCommand`.
    """
    stripped = line.strip()
    if not stripped:
        return None
    if not stripped.startswith("/"):
        return [f"Unknown command: {stripped}. Type /help for commands."]
    try:
        parts = shlex.split(stripped)
    except ValueError as exc:
        return [f"Command parse error: {exc}"]
    if not parts:
        return ["Type /help for commands."]
    return ParsedCommand(parts[0].lower(), parts[1:])


class TabState:
    """Active-tab index for the current tabbed screen.

    Keyed by an opaque screen key so the index auto-resets to the first tab
    whenever the active screen changes — navigating away and back to a tabbed
    screen starts on its first tab.
    """

    def __init__(self) -> None:
        """Create tab state positioned at the first tab of no screen yet."""
        self._index = 0
        self._key: str | None = None

    def active(self, key: str) -> int:
        """Return the active tab index for screen *key*, resetting on change."""
        if self._key != key:
            self._index = 0
            self._key = key
        return self._index

    def cycle(self, key: str, step: int, count: int) -> None:
        """Advance the active tab of screen *key* by *step* (wrapping).

        Args:
            key: The screen the tab index applies to.
            step: Signed number of tabs to move.
            count: Total tabs on the screen; a non-positive value is a no-op.
        """
        if count <= 0:
            return
        self._index = (self.active(key) + step) % count


@runtime_checkable
class Screen(Protocol):
    """One screen's behaviour: rendering, commands, hotkeys, and navigation.

    Applications implement this for each screen. Every method returns engine-level
    types — display lines, the :data:`QUIT` sentinel, or ``None`` when an input is
    not handled — so the router never inspects domain state.
    """

    @property
    def key(self) -> str:
        """Stable identifier for this screen (used to key tab state and legends)."""

    @property
    def spec(self) -> ScreenSpec:
        """Capability/hint descriptor driving the footer and ``?`` legend."""

    async def render(self) -> list[str]:
        """Return the screen's display lines."""

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Handle a slash command; ``None`` when the verb is not handled here."""

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Handle a Ctrl-<letter> hotkey; ``None`` when it is not handled here."""

    async def activate(self, item: ListItem) -> list[str]:
        """Open the selected list *item* and return the resulting screen."""

    async def search(self, query: str) -> list[str]:
        """Return the screen filtered by an incremental ``/`` *query*."""

    @property
    def list_navigator(self) -> ListNavigator | None:
        """The active list navigator, or ``None`` when the screen has no list."""

    def is_navigable(self) -> bool:
        """Whether ``↑↓``/``Enter`` navigation currently applies."""

    def tab_count(self) -> int:
        """Number of tabs on the screen (0 when untabbed)."""


class ScreenRouter(ABC):  # pylint: disable=too-many-public-methods  # implements the ReplController drive surface; one method per interaction
    """Drive the active :class:`Screen`, implementing the generic part of
    :class:`~.controller.ReplController`.

    Subclasses implement :meth:`active_screen` (mapping the application's own
    navigation state to a screen) and may override :meth:`dispatch_global`,
    :meth:`hotkey_global`, and :meth:`after_navigation`. The router owns the
    shared modal controller, the pending status notice, and the active-tab state;
    everything else it forwards to whichever screen is active.

    The remaining :class:`~.controller.ReplController` members — ``quit_requested``,
    ``header``, ``start_quit_confirm``, and ``pop_context`` — depend on the
    application's navigation model and stay with the subclass.
    """

    def __init__(self, screen: ScreenManager) -> None:
        """Bind the router to *screen* and create its shared modal controller.

        Args:
            screen: Terminal screen manager for width-aware rendering and the
                modal's refresh callback.
        """
        self.screen = screen
        self.modal = ModalController(screen, self.refresh_with_notice)
        self._notice: tuple[str, str] | None = None
        self._tabs = TabState()

    # --- application hooks -------------------------------------------------

    @abstractmethod
    def active_screen(self) -> Screen:
        """Return the screen matching the application's current navigation."""

    async def dispatch_global(self, _verb: str, _args: list[str]) -> list[str] | str | None:
        """Handle a command available on every screen, or ``None`` to defer.

        The default defers everything to the active screen; subclasses override
        with real parameter names to service cross-screen commands.
        """
        return None

    async def hotkey_global(self, _key_text: str) -> list[str] | str | None:
        """Handle a hotkey available on every screen, or ``None`` to defer.

        The default defers everything to the active screen; subclasses override
        with a real parameter name to service cross-screen hotkeys.
        """
        return None

    def after_navigation(self) -> None:
        """Hook run after each command/hotkey/activation that may navigate.

        The default does nothing; applications override it to persist state.
        """

    # --- status notice -----------------------------------------------------

    def take_notice(self) -> tuple[str, str] | None:
        """Return and clear the pending ``(message, level)`` status notice."""
        notice, self._notice = self._notice, None
        return notice

    def set_notice(self, message: str, level: str = "success") -> None:
        """Set the pending status notice without re-rendering."""
        self._notice = (message, level)

    async def refresh_with_notice(self, message: str, level: str = "success") -> list[str]:
        """Set a transient status notice and re-render the current screen."""
        self._notice = (message, level)
        return await self.render_current()

    # --- rendering & dispatch ---------------------------------------------

    async def render_current(self) -> list[str]:
        """Return the active screen's display lines."""
        return await self.active_screen().render()

    async def dispatch(self, command: str) -> list[str] | str:
        """Execute a ``:`` command line, then run :meth:`after_navigation`.

        Global commands are offered first, then the active screen. An unhandled
        verb yields a generic "unknown command" message.
        """
        parsed = parse_command(command)
        if parsed is None:
            return await self.render_current()
        if isinstance(parsed, list):
            return parsed
        result = await self.dispatch_global(parsed.verb, parsed.args)
        if result is None:
            result = await self.active_screen().run_command(parsed.verb, parsed.args)
        if result is None:
            result = [f"Unknown command: {parsed.verb}. Type /help for commands."]
        self.after_navigation()
        return result

    async def activate_list_selection(self, item: ListItem) -> list[str]:
        """Open the selected list *item*, then run :meth:`after_navigation`."""
        lines = await self.active_screen().activate(item)
        self.after_navigation()
        return lines

    async def search(self, query: str) -> list[str]:
        """Return the active screen filtered by an incremental ``/`` *query*."""
        return await self.active_screen().search(query)

    async def handle_hotkey(self, key_text: str) -> list[str] | str | None:
        """Route a hotkey (global first, then the active screen), then sync.

        Returns ``None`` when neither handles the key, so the loop ignores it.
        """
        result = await self.hotkey_global(key_text)
        if result is None:
            result = await self.active_screen().run_hotkey(key_text)
        self.after_navigation()
        return result

    # --- screen capabilities ----------------------------------------------

    def is_navigable(self) -> bool:
        """Whether ``↑↓``/``Enter`` navigation applies to the active screen."""
        return self.active_screen().is_navigable()

    def supports_search(self) -> bool:
        """Whether incremental ``/`` search applies to the active screen."""
        return self.active_screen().spec.searchable

    def tab_hint(self) -> str | None:
        """Return the active screen's tab grammar hint, or ``None`` if untabbed."""
        return self.active_screen().spec.tab_hint

    def tab_count(self) -> int:
        """Return the number of tabs on the active screen (0 when untabbed)."""
        return self.active_screen().tab_count()

    def active_tab(self) -> int:
        """Return the active tab index for the active screen."""
        return self._tabs.active(self.active_screen().key)

    def cycle_active_tab(self, step: int) -> None:
        """Advance the active tab by *step* (wrapping) on the active screen."""
        active = self.active_screen()
        self._tabs.cycle(active.key, step, active.tab_count())

    def command_hints(self) -> str:
        """Return the info-line action legend for the active screen.

        The info line carries *screen actions* only: the Ctrl-hotkey actions from
        the screen's :class:`ScreenSpec` plus its back entry. Interaction grammar
        belongs to the nav-hint line and is deliberately excluded here.
        """
        spec = self.active_screen().spec
        return " · ".join([*spec.actions, spec.back])

    def help_legend(self) -> list[str]:
        """Return the full control legend lines for the active screen (``?``)."""
        active = self.active_screen()
        return [f"Controls · {active.key}", "", *screen_controls(active.spec)]

    # --- navigation list ---------------------------------------------------

    @property
    def list_navigator(self) -> ListNavigator | None:
        """The active screen's list navigator, or ``None``."""
        return self.active_screen().list_navigator

    # --- modal: guided prompt ---------------------------------------------

    @property
    def prompt_state(self) -> PromptState | None:
        """The active guided-prompt state, or ``None``."""
        return self.modal.prompt_state

    def prompt_prefill(self) -> str:
        """Return the editable initial text for the active prompt field."""
        return self.modal.prompt_prefill()

    async def advance_prompt(self, value: str) -> list[str]:
        """Submit *value* to the active guided prompt."""
        return await self.modal.advance_prompt(value)

    def prompt_move(self, direction: str) -> list[str]:
        """Move the active select field's highlight ``"up"`` or ``"down"``."""
        return self.modal.prompt_move(direction)

    async def submit_prompt_selection(self) -> list[str]:
        """Submit the highlighted option of the active select field."""
        return await self.modal.submit_prompt_selection()

    async def cancel_prompt(self) -> list[str]:
        """Cancel the active guided prompt and restore the current screen."""
        return await self.modal.cancel_prompt()

    # --- modal: typeahead picker ------------------------------------------

    @property
    def picker_state(self) -> PickerState | None:
        """The active typeahead-picker state, or ``None``."""
        return self.modal.picker_state

    def update_picker_query(self, query: str) -> list[str]:
        """Re-filter the active picker for *query*."""
        return self.modal.update_picker_query(query)

    def picker_move(self, direction: str) -> list[str]:
        """Move the picker highlight ``"up"`` or ``"down"``."""
        return self.modal.picker_move(direction)

    async def picker_select(self) -> list[str]:
        """Choose the highlighted match and invoke the picker callback."""
        return await self.modal.picker_select()

    async def cancel_picker(self) -> list[str]:
        """Cancel the active typeahead picker and restore the current screen."""
        return await self.modal.cancel_picker()
