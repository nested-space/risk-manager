"""Unit tests for the layout stacking containers (vstack, hstack, card_row)."""

import pytest

from riskmanager_cli.repl.renderers.layout.geometry import block_width, visible_len
from riskmanager_cli.repl.renderers.layout.stacks import (
    card_row,
    center_block,
    hstack,
    join_horizontal,
    vstack,
)
from riskmanager_cli.repl.viewport import parse


@pytest.mark.unit
def test_vstack_inserts_gap_rows_between_children() -> None:
    """A gap inserts that many blank rows between adjacent children only."""
    assert vstack([["a"], ["b"]], gap=2) == ["a", "", "", "b"]


@pytest.mark.unit
def test_vstack_centres_each_child_as_a_unit() -> None:
    """Centre alignment shifts each child by one shared margin within the width."""
    assert vstack([["xx"], ["y"]], align="center", width=6) == ["  xx", "  y"]


@pytest.mark.unit
def test_center_block_matches_vstack_centre() -> None:
    """``center_block`` is the single-child centre case."""
    assert center_block(["ab"], 6) == vstack([["ab"]], align="center", width=6)


@pytest.mark.unit
def test_hstack_joins_side_by_side_with_gap() -> None:
    """Children sit side by side, each padded to its own width, gap between."""
    assert hstack([["ab"], ["cd"]], gap=1) == ["ab cd"]


@pytest.mark.unit
def test_hstack_pads_ragged_heights_by_valign() -> None:
    """A shorter child is padded to the row height per the vertical alignment."""
    top = hstack([["a", "b"], ["c"]], gap=0, align="top")
    assert top == ["ac", "b "]
    bottom = hstack([["a", "b"], ["c"]], gap=0, align="bottom")
    assert bottom == ["a ", "bc"]


@pytest.mark.unit
def test_join_horizontal_is_top_aligned_hstack() -> None:
    """The historical helper reproduces a top-aligned row."""
    blocks = [["a", "b"], ["c"]]
    assert join_horizontal(blocks, 1) == hstack(blocks, gap=1, align="top")


@pytest.mark.unit
def test_hstack_aligns_styled_blocks_by_visible_width() -> None:
    """A styled child is padded by its printable width so columns line up."""
    styled = ["\x1b[1mab\x1b[0m"]
    row = hstack([styled, ["c"]], gap=1)
    assert visible_len(row[0]) == block_width(styled) + 1 + 1


@pytest.mark.unit
def test_card_row_tags_selection_in_row_layout() -> None:
    """In a row the whole block is the selection; nothing is tagged when none."""
    boxes = [["A"], ["B"], ["C"]]
    tagged = parse(card_row(boxes, width=20, gap=2, selected_index=1, stacked=False))
    assert tagged.selected is not None
    untagged = parse(card_row(boxes, width=20, gap=2, selected_index=-1, stacked=False))
    assert untagged.selected is None


@pytest.mark.unit
def test_card_row_stacked_tags_only_selected_card() -> None:
    """Stacked, only the selected card's lines carry the selection tag."""
    boxes = [["A"], ["B"], ["C"]]
    view = parse(card_row(boxes, width=10, gap=1, selected_index=2, stacked=True))
    assert view.selected is not None
    start, end = view.selected
    assert "C" in "\n".join(view.lines[start : end + 1])
    assert "A" not in "\n".join(view.lines[start : end + 1])
