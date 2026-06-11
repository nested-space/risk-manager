"""Unit tests for ScreenManager layout and the bottom information line."""

import pytest

from riskmanager_cli.repl.context import ContextManager
from riskmanager_cli.repl.screen import ScreenManager


class _FakeTerminal:
    """Minimal blessed.Terminal stand-in exposing the attributes ScreenManager uses."""

    # Styling sequences collapse to empty strings so captured output is plain text.
    clear_eol = ""
    dim = ""
    normal = ""
    on_blue = ""
    bold = ""
    white = ""
    green = ""
    red = ""
    yellow = ""
    home = ""
    clear = ""

    def __init__(self, width: int = 80, height: int = 24) -> None:
        self.width = width
        self.height = height

    def move_xy(self, _x: int, _y: int) -> str:
        """Return the (no-op) cursor-move sequence."""
        return ""

    def length(self, text: str) -> int:
        """Return the printable length (styling collapses to empty strings here)."""
        return len(text)


@pytest.mark.unit
def test_output_height_reserves_status_input_and_info_rows() -> None:
    """The output pane is the terminal height minus the four reserved rows."""
    screen = ScreenManager(_FakeTerminal(height=24), ContextManager())  # type: ignore[arg-type]
    assert screen.output_height == 20


@pytest.mark.unit
def test_output_height_clamps_to_zero_on_tiny_terminal() -> None:
    """A terminal too short for any output pane reports zero rows, not negative."""
    screen = ScreenManager(_FakeTerminal(height=2), ContextManager())  # type: ignore[arg-type]
    assert screen.output_height == 0


@pytest.mark.unit
def test_draw_info_line_truncates_with_ellipsis(capsys: pytest.CaptureFixture[str]) -> None:
    """A hint wider than the terminal is truncated and ends with an ellipsis."""
    screen = ScreenManager(_FakeTerminal(width=10), ContextManager())  # type: ignore[arg-type]
    screen.draw_info_line("/aaa · /bbb · /ccc · /ddd")
    out = capsys.readouterr().out
    assert out.endswith("…")
    assert len(out) == 10


@pytest.mark.unit
def test_draw_info_line_keeps_short_hint_intact(capsys: pytest.CaptureFixture[str]) -> None:
    """A hint that fits within the width is rendered verbatim without an ellipsis."""
    screen = ScreenManager(_FakeTerminal(width=40), ContextManager())  # type: ignore[arg-type]
    screen.draw_info_line("/home · /quit")
    out = capsys.readouterr().out
    assert out == "/home · /quit"


@pytest.mark.unit
def test_draw_input_line_right_aligns_notice(capsys: pytest.CaptureFixture[str]) -> None:
    """A notice is padded to the right edge of the input row when there is room."""
    screen = ScreenManager(_FakeTerminal(width=20), ContextManager())  # type: ignore[arg-type]
    screen.draw_input_line(text="hi", notice=screen.style_notice("Saved", "success"))
    out = capsys.readouterr().out
    assert out.startswith("> hi")
    assert out.endswith("Saved")
    assert len(out) == 20


@pytest.mark.unit
def test_draw_input_line_drops_notice_without_room(capsys: pytest.CaptureFixture[str]) -> None:
    """When the typed text leaves no gap, the notice is dropped and input preserved."""
    screen = ScreenManager(_FakeTerminal(width=8), ContextManager())  # type: ignore[arg-type]
    screen.draw_input_line(text="typing", notice=screen.style_notice("Saved", "success"))
    out = capsys.readouterr().out
    assert out == "> typing"
    assert "Saved" not in out
