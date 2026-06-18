"""Unit tests for the generic screen-dispatch engine."""

from __future__ import annotations

import pytest

from riskmanager_cli.repl_engine.dispatch import (
    ParsedCommand,
    Screen,
    ScreenRouter,
    ScreenSpec,
    TabState,
    parse_command,
    screen_controls,
)
from riskmanager_cli.repl_engine.list_navigator import ListItem, ListNavigator
from riskmanager_cli.repl_engine.screen import ScreenManager


class _FakeTerminal:
    """Minimal blessed.Terminal stand-in sufficient to build a ScreenManager."""

    clear_eol = dim = normal = on_blue = bold = white = green = red = yellow = ""
    home = clear = ""

    def __init__(self, width: int = 80, height: int = 24) -> None:
        self.width = width
        self.height = height

    def move_xy(self, _x: int, _y: int) -> str:
        return ""

    def length(self, text: str) -> int:
        return len(text)


class _FakeScreen:
    """A scriptable :class:`Screen` recording the calls the router makes."""

    def __init__(self, key: str, spec: ScreenSpec) -> None:
        self._key = key
        self._spec = spec
        self.navigator: ListNavigator | None = None
        self.tabs = 0
        self.commands: list[tuple[str, list[str]]] = []
        self.hotkeys: list[str] = []
        self.activated: list[str] = []
        self.searched: list[str] = []
        self.command_result: list[str] | str | None = ["ran"]
        self.hotkey_result: list[str] | str | None = ["hot"]

    @property
    def key(self) -> str:
        return self._key

    @property
    def spec(self) -> ScreenSpec:
        return self._spec

    async def render(self) -> list[str]:
        return [f"render:{self._key}"]

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        self.commands.append((verb, args))
        return self.command_result

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        self.hotkeys.append(key_text)
        return self.hotkey_result

    async def activate(self, item: ListItem) -> list[str]:
        self.activated.append(item.item_id)
        return [f"open:{item.item_id}"]

    async def search(self, query: str) -> list[str]:
        self.searched.append(query)
        return [f"search:{query}"]

    @property
    def list_navigator(self) -> ListNavigator | None:
        return self.navigator

    def is_navigable(self) -> bool:
        return self._spec.navigable

    def tab_count(self) -> int:
        return self.tabs


class _Router(ScreenRouter):
    """Concrete router over a single fake screen, with recording hooks."""

    def __init__(self, screen_obj: _FakeScreen) -> None:
        super().__init__(ScreenManager(_FakeTerminal()))
        self._screen_obj = screen_obj
        self.synced = 0
        self.global_verbs: list[str] = []
        self.global_keys: list[str] = []
        self.global_command_result: list[str] | str | None = None
        self.global_hotkey_result: list[str] | str | None = None

    def active_screen(self) -> Screen:
        return self._screen_obj

    def after_navigation(self) -> None:
        self.synced += 1

    async def dispatch_global(self, verb: str, args: list[str]) -> list[str] | str | None:
        self.global_verbs.append(verb)
        return self.global_command_result

    async def hotkey_global(self, key_text: str) -> list[str] | str | None:
        self.global_keys.append(key_text)
        return self.global_hotkey_result


def _spec(**kwargs: object) -> ScreenSpec:
    base = {"navigable": False, "searchable": False, "actions": ()}
    base.update(kwargs)
    return ScreenSpec(**base)  # type: ignore[arg-type]


# --- parse_command -----------------------------------------------------------


@pytest.mark.unit
def test_parse_command_blank_returns_none() -> None:
    """A blank line signals the caller to re-render rather than dispatch."""
    assert parse_command("   ") is None


@pytest.mark.unit
def test_parse_command_non_slash_returns_message() -> None:
    """Free text that is not a command yields a guidance message."""
    result = parse_command("hello")
    assert isinstance(result, list)
    assert "Unknown command" in result[0]


@pytest.mark.unit
def test_parse_command_unbalanced_quotes_returns_error() -> None:
    """A tokenisation failure is reported as a message, not an exception."""
    result = parse_command('/add "unterminated')
    assert isinstance(result, list)
    assert "parse error" in result[0]


@pytest.mark.unit
def test_parse_command_splits_verb_and_args_lowercasing_verb() -> None:
    """A valid command lowercases the verb and keeps argument case."""
    parsed = parse_command("/Add Stage Foo")
    assert parsed == ParsedCommand("/add", ["Stage", "Foo"])


# --- screen_controls ---------------------------------------------------------


@pytest.mark.unit
def test_screen_controls_orders_grammar_then_actions() -> None:
    """The legend lists interaction grammar first, then actions and back."""
    spec = _spec(navigable=True, searchable=True, actions=("^A add",), back="^C quit")
    assert screen_controls(spec) == [
        "↑↓ navigate",
        "Enter select",
        "/ search",
        ": command",
        "? help",
        "^A add",
        "^C quit",
    ]


@pytest.mark.unit
def test_screen_controls_omits_absent_grammar() -> None:
    """A non-navigable, non-searchable screen shows only command/help + back."""
    assert screen_controls(_spec()) == [": command", "? help", "^C back"]


# --- TabState ----------------------------------------------------------------


@pytest.mark.unit
def test_tab_state_resets_index_when_screen_changes() -> None:
    """Switching screen keys resets the active tab to the first tab."""
    tabs = TabState()
    tabs.cycle("a", 1, 3)
    assert tabs.active("a") == 1
    assert tabs.active("b") == 0  # different screen resets


@pytest.mark.unit
def test_tab_state_cycle_wraps_and_ignores_untabbed() -> None:
    """Cycling wraps modulo count; a non-positive count is a no-op."""
    tabs = TabState()
    tabs.cycle("a", 1, 2)
    tabs.cycle("a", 1, 2)
    assert tabs.active("a") == 0  # wrapped 0->1->0
    tabs.cycle("a", 1, 0)
    assert tabs.active("a") == 0


# --- ScreenRouter dispatch ---------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_blank_renders_current() -> None:
    """An empty command line re-renders the active screen."""
    screen = _FakeScreen("home", _spec())
    router = _Router(screen)
    assert await router.dispatch("") == ["render:home"]
    assert screen.commands == []


@pytest.mark.asyncio
async def test_dispatch_prefers_global_then_screen() -> None:
    """A global handler wins; otherwise the active screen runs the command."""
    screen = _FakeScreen("home", _spec())
    router = _Router(screen)

    router.global_command_result = ["global"]
    assert await router.dispatch("/quit") == ["global"]
    assert screen.commands == []  # screen never consulted

    router.global_command_result = None
    assert await router.dispatch("/list things") == ["ran"]
    assert screen.commands == [("/list", ["things"])]
    assert router.synced == 2  # after_navigation ran each time


@pytest.mark.asyncio
async def test_dispatch_unhandled_verb_reports_unknown() -> None:
    """When neither global nor screen handle the verb, a message is returned."""
    screen = _FakeScreen("home", _spec())
    screen.command_result = None
    router = _Router(screen)
    result = await router.dispatch("/bogus")
    assert isinstance(result, list)
    assert "Unknown command: /bogus" in result[0]


@pytest.mark.asyncio
async def test_handle_hotkey_defers_to_screen_and_syncs() -> None:
    """An unhandled global hotkey falls through to the active screen."""
    screen = _FakeScreen("home", _spec())
    router = _Router(screen)
    assert await router.handle_hotkey("\x01") == ["hot"]
    assert screen.hotkeys == ["\x01"]
    assert router.synced == 1


@pytest.mark.asyncio
async def test_activate_list_selection_delegates_and_syncs() -> None:
    """Activation opens the item on the active screen and runs after_navigation."""
    screen = _FakeScreen("home", _spec())
    router = _Router(screen)
    lines = await router.activate_list_selection(ListItem(label="P", item_id="p1"))
    assert lines == ["open:p1"]
    assert screen.activated == ["p1"]
    assert router.synced == 1


@pytest.mark.asyncio
async def test_search_delegates_without_syncing() -> None:
    """Search is read-only: it never triggers after_navigation."""
    screen = _FakeScreen("home", _spec(searchable=True))
    router = _Router(screen)
    assert await router.search("foo") == ["search:foo"]
    assert router.synced == 0


# --- ScreenRouter capabilities ----------------------------------------------


@pytest.mark.unit
def test_capabilities_derive_from_active_screen_spec() -> None:
    """Search/tab-hint/hints/legend all derive from the active screen's spec."""
    spec = _spec(navigable=True, searchable=True, actions=("^A add", "^E edit"), tab_hint="Tab")
    router = _Router(_FakeScreen("lib", spec))
    assert router.supports_search() is True
    assert router.is_navigable() is True
    assert router.tab_hint() == "Tab"
    assert router.command_hints() == "^A add · ^E edit · ^C back"
    assert router.help_legend()[0] == "Controls · lib"


@pytest.mark.unit
def test_cycle_active_tab_uses_screen_tab_count() -> None:
    """Tab cycling respects the active screen's reported tab count."""
    screen = _FakeScreen("lib", _spec())
    screen.tabs = 2
    router = _Router(screen)
    assert router.tab_count() == 2
    router.cycle_active_tab(1)
    assert router.active_tab() == 1


# --- ScreenRouter modal + notice --------------------------------------------


@pytest.mark.unit
def test_take_notice_returns_then_clears() -> None:
    """A set notice is returned once and then cleared."""
    router = _Router(_FakeScreen("home", _spec()))
    router.set_notice("done", "success")
    assert router.take_notice() == ("done", "success")
    assert router.take_notice() is None


@pytest.mark.unit
def test_modal_state_delegates_to_controller() -> None:
    """With no active modal, the router reports the controller's empty state."""
    router = _Router(_FakeScreen("home", _spec()))
    assert router.prompt_state is None
    assert router.picker_state is None
    assert router.list_navigator is None
