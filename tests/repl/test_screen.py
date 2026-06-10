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
    home = ""
    clear = ""

    def __init__(self, width: int = 80, height: int = 24) -> None:
        self.width = width
        self.height = height

    def move_xy(self, _x: int, _y: int) -> str:
        """Return the (no-op) cursor-move sequence."""
        return ""


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
