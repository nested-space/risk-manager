"""Unit tests for the responsive landing-screen renderer."""

from collections.abc import Callable

import pytest

from riskmanager_cli.repl.renderers.home_renderer import render_home
from riskmanager_cli.repl.viewport import parse

_TITLES = ("P R O J E C T", "L I B R A R Y", "A D M I N")


def _identity(text: str) -> str:
    return text


def _render(selected_index: int = -1, *, width: int, bold: Callable[[str], str] = _identity):
    """Render the home screen and return the clean (tag-stripped) display lines."""
    return parse(render_home(selected_index, width=width, bold=bold)).lines


@pytest.mark.unit
def test_render_home_wide_uses_full_banner_and_row_layout() -> None:
    """A wide terminal shows the block banner with all cards on one row."""
    lines = _render(width=100)
    assert any("█" in line for line in lines)  # full block banner
    # Side by side: a single line carries all three card titles.
    assert any(all(title in line for title in _TITLES) for line in lines)


@pytest.mark.unit
def test_render_home_medium_width_uses_figlet_banner() -> None:
    """Between the full block and the framed title, a mid-size figlet is shown."""
    lines = _render(width=80)
    assert not any("█" in line or "║" in line for line in lines)
    assert any("|___/" in line for line in lines)  # figlet 'g' descender


@pytest.mark.unit
def test_render_home_small_width_uses_framed_title() -> None:
    """Below the figlet width, the small framed title is shown."""
    lines = _render(width=40)
    assert not any("█" in line for line in lines)
    assert any("R I S K   M A N A G E R" in line for line in lines)


@pytest.mark.unit
def test_render_home_narrow_stacks_cards() -> None:
    """Below the row breakpoint the cards stack vertically."""
    lines = _render(width=50)
    # No line holds two titles: the cards are stacked, not side by side.
    assert not any(sum(title in line for title in _TITLES) > 1 for line in lines)
    text = "\n".join(lines)
    assert all(title in text for title in _TITLES)


@pytest.mark.unit
def test_render_home_very_narrow_uses_plain_title() -> None:
    """A very narrow terminal falls back to the bare text title."""
    lines = _render(width=20)
    assert not any("█" in line or "║" in line for line in lines)
    assert any(line.strip() == "RISK MANAGER" for line in lines)


@pytest.mark.unit
@pytest.mark.parametrize("width", range(24, 130))
def test_render_home_never_exceeds_drawable_width(width: int) -> None:
    """No line overruns the output pane's drawable area (one margin each side).

    Regression: the layout previously sized to the full width while the pane
    draws from column 1 and clips at ``width - 2``, so the rightmost card and
    banner column were clipped in a band just below where the row stops fitting.
    """
    lines = _render(width=width)
    assert max(len(line) for line in lines) <= width - 2


@pytest.mark.unit
def test_render_home_bolds_only_the_selected_card() -> None:
    """The bold styler is applied solely to the highlighted card."""
    plain = _render(-1, width=100, bold=lambda s: f"<{s}>")
    assert not any("<" in line for line in plain)

    selected = _render(0, width=100, bold=lambda s: f"<{s}>")
    assert any("<" in line for line in selected)


@pytest.mark.unit
def test_render_home_pins_banner_and_marks_selected_card() -> None:
    """The banner is sticky and the focused card is the tagged selection."""
    view = parse(render_home(2, width=45, bold=_identity))
    assert view.sticky_count > 0  # banner pinned
    # The selection range covers the ADMIN card, not PROJECT/LIBRARY.
    assert view.selected is not None
    start, end = view.selected
    selected_text = "\n".join(view.lines[start : end + 1])
    assert "A D M I N" in selected_text
    assert "P R O J E C T" not in selected_text
