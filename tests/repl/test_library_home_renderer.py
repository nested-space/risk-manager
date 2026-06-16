"""Unit tests for the Library home-page renderer."""

from collections.abc import Callable

import pytest

from riskmanager_cli.repl.renderers.library_home_renderer import (
    OVERVIEW_CARDS,
    render_library_home,
)
from riskmanager_cli.repl.viewport import parse

_COUNTS = {"ncrm": 42, "materials": 18, "counterions": 5}


def _identity(text: str) -> str:
    return text


def _render(
    selected_index: int = -1, *, width: int = 100, bold: Callable[[str], str] = _identity
) -> list[str]:
    """Render the library home and return the clean (tag-stripped) display lines."""
    return parse(render_library_home(_COUNTS, selected_index, width=width, bold=bold)).lines


@pytest.mark.unit
def test_render_library_home_shows_title_sections_and_counts() -> None:
    """The page carries the title, both section rules, bullets and every count."""
    lines = _render(width=100)
    text = "\n".join(lines)
    assert "Risk Manager Library" in text
    assert "About This Tool" in text
    assert "Database Overview" in text
    assert "Currently Supported" in text
    assert "Not Yet Supported" in text
    # A bullet from each info card survives wrapping.
    assert "Create, Read, Update" in text
    assert "Chemical structure visualisation" in text
    # All three subsection counts are rendered.
    for count in _COUNTS.values():
        assert any(str(count) in line for line in lines)
    # All three card titles are present.
    for _key, title in OVERVIEW_CARDS:
        assert title in text


@pytest.mark.unit
def test_render_library_home_bolds_only_selected_card() -> None:
    """The bold styler marks only the highlighted overview card."""
    plain = _render(-1, width=100, bold=lambda s: f"<{s}>")
    assert not any("<" in line for line in plain)

    # Narrow enough that the cards stack, so the highlight stays on one card.
    selected = _render(0, width=45, bold=lambda s: f"<{s}>")
    bolded = "\n".join(line for line in selected if "<" in line)
    assert "NCRMs" in bolded  # first OVERVIEW_CARDS entry
    assert "Materials" not in bolded


@pytest.mark.unit
def test_render_library_home_pins_title_and_marks_selected_card() -> None:
    """The title is sticky and the focused overview card is the tagged selection."""
    # A stacked width keeps each card on its own row so the selection is isolated.
    view = parse(render_library_home(_COUNTS, 2, width=45, bold=_identity))
    assert view.sticky_count > 0  # title pinned
    assert view.lines[0] == "Risk Manager Library"
    assert view.selected is not None
    start, end = view.selected
    selected_text = "\n".join(view.lines[start : end + 1])
    assert "Counterions" in selected_text  # third card
    assert "NCRMs" not in selected_text


@pytest.mark.unit
def test_render_library_home_missing_count_renders_zero() -> None:
    """A subsection absent from the counts map renders as 0 rather than erroring."""
    # Stacked so each count sits alone in its card, framed by box borders.
    lines = parse(render_library_home({"ncrm": 3}, -1, width=45, bold=_identity)).lines
    cells = [line.strip("│ ") for line in lines]
    assert "3" in cells  # the supplied ncrm count
    assert cells.count("0") == 2  # materials and counterions default to zero


@pytest.mark.unit
@pytest.mark.parametrize("width", range(28, 130))
def test_render_library_home_never_exceeds_drawable_width(width: int) -> None:
    """No line overruns the output pane's drawable area (one margin each side)."""
    lines = _render(width=width)
    assert max(len(line) for line in lines) <= width - 2


@pytest.mark.unit
def test_render_library_home_narrow_stacks_overview_cards() -> None:
    """Below the row breakpoint the overview cards stack vertically."""
    lines = _render(width=40)
    titles = [title for _key, title in OVERVIEW_CARDS]
    # No single line carries two card titles: the cards are stacked.
    assert not any(sum(title in line for title in titles) > 1 for line in lines)
    text = "\n".join(lines)
    assert all(title in text for title in titles)
