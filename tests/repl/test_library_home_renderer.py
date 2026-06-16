"""Unit tests for the Library home-page renderer (tabbed overview/information)."""

from collections.abc import Callable

import pytest

from riskmanager_cli.repl.renderers.library_home_renderer import (
    LIBRARY_HOME_TABS,
    OVERVIEW_CARDS,
    render_library_home,
)
from riskmanager_cli.repl.viewport import parse

_COUNTS = {"ncrm": 42, "materials": 18, "counterions": 5}

# Below this terminal width the tab strip ("Libraries"/"Information") can no longer
# fit, so the renderer's no-overflow guarantee only holds at or above it; narrower
# terminals are clipped by the screen manager when drawn.
_MIN_WIDTH = 29


def _identity(text: str) -> str:
    return text


def _render(
    selected_index: int = -1,
    *,
    active_tab: int = 0,
    width: int = 100,
    bold: Callable[[str], str] = _identity,
) -> list[str]:
    """Render the library home and return the clean (tag-stripped) display lines."""
    return parse(
        render_library_home(_COUNTS, selected_index, active_tab=active_tab, width=width, bold=bold)
    ).lines


@pytest.mark.unit
def test_render_library_home_libraries_tab_shows_title_tabs_and_counts() -> None:
    """The Libraries tab carries the title, both tab labels and every count/card."""
    lines = _render(active_tab=0, width=100)
    text = "\n".join(lines)
    assert "Risk Manager Library" in text
    # The About paragraph survives wrapping.
    assert "draws on" in text
    # Both tab labels are drawn.
    for tab in LIBRARY_HOME_TABS:
        assert tab in text
    # All three subsection counts are rendered.
    for count in _COUNTS.values():
        assert any(str(count) in line for line in lines)
    # All three card titles are present.
    for _key, title in OVERVIEW_CARDS:
        assert title in text


@pytest.mark.unit
def test_render_library_home_information_tab_shows_capabilities() -> None:
    """The Information tab lists the supported / not-yet-supported capabilities."""
    text = "\n".join(_render(active_tab=1, width=100))
    assert "Currently Supported" in text
    assert "Not Yet Supported" in text
    # A bullet from each info card survives wrapping.
    assert "Create, Read, Update" in text
    assert "Chemical structure visualisation" in text
    # The tab labels are still drawn on the Information tab.
    for tab in LIBRARY_HOME_TABS:
        assert tab in text


@pytest.mark.unit
def test_render_library_home_bolds_only_selected_card() -> None:
    """The bold styler marks the highlighted overview card, not the others."""

    def line_with(lines: list[str], token: str) -> str:
        # The card title line is framed by box borders, distinguishing it from the
        # same word appearing in the About paragraph prose.
        return next(line for line in lines if token in line and "│" in line)

    # Narrow enough that the cards stack, so the highlight stays on one card.
    plain = _render(-1, width=45, bold=lambda s: f"<{s}>")
    assert "<" not in line_with(plain, "NCRMs")  # nothing selected → no card bolded

    selected = _render(0, width=45, bold=lambda s: f"<{s}>")
    assert "<" in line_with(selected, "NCRMs")  # first OVERVIEW_CARDS entry, bolded
    assert "<" not in line_with(selected, "Materials")


@pytest.mark.unit
def test_render_library_home_pins_title_and_marks_selected_card() -> None:
    """The title is sticky and the focused overview card is the tagged selection."""
    # A stacked width keeps each card on its own row so the selection is isolated.
    view = parse(render_library_home(_COUNTS, 2, active_tab=0, width=45, bold=_identity))
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
    # Stacked so each count sits alone in its card cell, framed by box borders.
    rendered = render_library_home({"ncrm": 3}, -1, active_tab=0, width=45, bold=_identity)
    lines = parse(rendered).lines
    cells = [segment.strip() for line in lines for segment in line.split("│")]
    assert cells.count("3") == 1  # the supplied ncrm count
    assert cells.count("0") == 2  # materials and counterions default to zero


@pytest.mark.unit
@pytest.mark.parametrize("active_tab", [0, 1])
@pytest.mark.parametrize("width", range(_MIN_WIDTH, 130))
def test_render_library_home_never_exceeds_drawable_width(active_tab: int, width: int) -> None:
    """No line overruns the output pane's drawable area (one margin each side)."""
    lines = _render(active_tab=active_tab, width=width)
    assert max(len(line) for line in lines) <= width - 2


@pytest.mark.unit
def test_render_library_home_narrow_stacks_overview_cards() -> None:
    """Below the row breakpoint the overview cards stack vertically."""
    lines = _render(active_tab=0, width=40)
    titles = [title for _key, title in OVERVIEW_CARDS]
    # No single line carries two card titles: the cards are stacked.
    assert not any(sum(title in line for title in titles) > 1 for line in lines)
    text = "\n".join(lines)
    assert all(title in text for title in titles)
