"""Unit tests for the layout geometry foundation (width measurement, padding)."""

import pytest

from riskmanager_cli.repl.renderers.layout.geometry import (
    block_width,
    pad_block,
    pad_line,
    visible_len,
)

_STYLED = "\x1b[1mHello\x1b[0m"  # "Hello" wrapped in bold/reset escapes


@pytest.mark.unit
def test_visible_len_ignores_ansi_escapes() -> None:
    """Visible width counts printable columns only, not escape sequences."""
    assert visible_len(_STYLED) == 5
    assert visible_len("plain") == 5


@pytest.mark.unit
def test_block_width_is_widest_visible_line() -> None:
    """A block's width is its widest line measured by visible columns."""
    assert block_width([_STYLED, "a", "abcd"]) == 5
    assert block_width([]) == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("align", "expected"),
    [("left", "ab   "), ("right", "   ab"), ("center", " ab  ")],
)
def test_pad_line_aligns_within_width(align: str, expected: str) -> None:
    """A line is padded with spaces on the side(s) implied by the alignment."""
    assert pad_line("ab", 5, align) == expected  # type: ignore[arg-type]


@pytest.mark.unit
def test_pad_line_never_clips() -> None:
    """A line already at or beyond the width is returned unchanged."""
    assert pad_line("abcdef", 4, "left") == "abcdef"


@pytest.mark.unit
def test_pad_line_pads_by_visible_width() -> None:
    """Padding measures the styled line by its printable width (5), adding 2."""
    assert visible_len(pad_line(_STYLED, 7, "left")) == 7


@pytest.mark.unit
def test_pad_block_fills_exact_width_and_height() -> None:
    """The block is padded to an exact width × height rectangle of cells."""
    rows = pad_block(["ab", "c"], 4, 3)
    assert rows == ["ab  ", "c   ", "    "]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("valign", "expected"),
    [
        ("top", ["x ", "  ", "  "]),
        ("middle", ["  ", "x ", "  "]),
        ("bottom", ["  ", "  ", "x "]),
    ],
)
def test_pad_block_vertical_alignment(valign: str, expected: list[str]) -> None:
    """Blank fill rows are added above/below per the vertical alignment."""
    assert pad_block(["x"], 2, 3, valign=valign) == expected  # type: ignore[arg-type]


@pytest.mark.unit
def test_pad_block_does_not_truncate() -> None:
    """A block already taller than the target height keeps all its rows."""
    rows = pad_block(["a", "b", "c"], 1, 1)
    assert len(rows) == 3
