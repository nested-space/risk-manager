"""Unit tests for the selection-aware viewport model."""

import pytest

from riskmanager_cli.repl_engine.viewport import (
    follow,
    max_offset,
    parse,
    selected_line,
    tag_selected,
    tag_sticky,
    window,
)


@pytest.mark.unit
def test_parse_untagged_buffer_is_plain() -> None:
    """A buffer with no tags has no sticky region and no selection."""
    view = parse(["a", "b", "c"])
    assert view.lines == ["a", "b", "c"]
    assert view.sticky_count == 0
    assert view.selected is None


@pytest.mark.unit
def test_parse_strips_tags_and_records_ranges() -> None:
    """Leading sticky lines and a tagged selection are recovered as ranges."""
    raw = [*tag_sticky(["BANNER1", "BANNER2"]), "", *tag_selected(["card-top", "card-bot"])]
    view = parse(raw)
    assert view.lines == ["BANNER1", "BANNER2", "", "card-top", "card-bot"]
    assert view.sticky_count == 2  # only the leading run is sticky
    assert view.selected == (3, 4)


@pytest.mark.unit
def test_parse_sticky_only_counts_leading_run() -> None:
    """A sticky tag after a normal line does not extend the pinned region."""
    raw = [*tag_sticky(["BANNER"]), "gap", *tag_sticky(["stray"])]
    view = parse(raw)
    assert view.sticky_count == 1


@pytest.mark.unit
def test_selected_line_prefers_tag_then_caret() -> None:
    """The tagged selection wins; otherwise a caret row is found."""
    assert selected_line(parse([*tag_selected(["x"]), "y"])) == 0
    assert selected_line(parse(["a", "▶ b", "c"])) == 1
    assert selected_line(parse(["a", "> b"])) == 1
    assert selected_line(parse(["a", "b"])) is None


@pytest.mark.unit
def test_window_pins_sticky_region_above_scrolled_body() -> None:
    """The sticky head stays put while the body scrolls beneath it."""
    raw = [*tag_sticky(["HEAD"]), "0", "1", "2", "3", "4"]
    view = parse(raw)
    drawn = window(view, offset=2, height=3)
    assert drawn[0] == "HEAD"  # pinned regardless of offset
    assert drawn[1:] == ["2", "3"]  # body shows from offset within remaining rows


@pytest.mark.unit
def test_window_without_sticky_is_a_plain_slice() -> None:
    """Untagged buffers behave exactly like a simple scrolled slice."""
    view = parse(["0", "1", "2", "3"])
    assert window(view, offset=1, height=2) == ["1", "2"]


@pytest.mark.unit
def test_max_offset_accounts_for_sticky_rows() -> None:
    """The scroll limit is over the body, against the reduced viewport height."""
    view = parse([*tag_sticky(["HEAD"]), "0", "1", "2", "3"])  # body length 4
    # Pane height 3 -> body viewport 2 -> max body offset 4 - 2 = 2.
    assert max_offset(view, height=3) == 2


@pytest.mark.unit
def test_follow_scrolls_selection_into_view_below_sticky() -> None:
    """A selection past the body viewport scrolls until it is visible."""
    raw = [*tag_sticky(["HEAD"]), "0", "1", "2", "3", *tag_selected(["SEL"])]
    view = parse(raw)  # body = [0,1,2,3,SEL]; SEL at body index 4
    offset = follow(view, offset=0, height=3)  # body viewport = 2 rows
    drawn = window(view, offset, height=3)
    assert drawn[0] == "HEAD"
    assert "SEL" in drawn


@pytest.mark.unit
def test_follow_keeps_visible_selection_steady() -> None:
    """A selection already on screen does not move the offset."""
    raw = [*tag_selected(["SEL"]), "1", "2", "3"]
    view = parse(raw)
    assert follow(view, offset=0, height=4) == 0


@pytest.mark.unit
def test_follow_pins_tall_selection_to_its_top() -> None:
    """A selection taller than the viewport shows its first line."""
    raw = ["pad", *tag_selected(["s0", "s1", "s2", "s3"])]
    view = parse(raw)  # selection body indices 1..4
    offset = follow(view, offset=0, height=2)  # viewport 2 rows < selection height
    drawn = window(view, offset, height=2)
    assert drawn[0] == "s0"  # top of the selection is kept visible
