"""Unit tests for the shared sectioned-screen layout with wrapped rows.

These cover the seam between the engine's wrapping primitive
(``render_table_blocks``) and the application's selectable-table layout: that a
wrapped row maps every physical line back to one ``item_id``, the caret sits on
the row's first line only, and the whole wrapped row is tagged so the viewport
keeps it on screen.
"""

from dataclasses import dataclass

import pytest

from riskmanager_cli.repl.renderers._sections import (
    frame_body_line,
    pair_table_lines,
    render_sectioned_screen,
    section_body,
)
from riskmanager_cli.repl_engine.layout import Column, render_table_blocks
from riskmanager_cli.repl_engine.viewport import follow, parse


@dataclass
class _Row:
    """A minimal :class:`~_sections.Row` for the tests."""

    item_id: str | None
    cells: list[str]


_WRAP_COLUMNS = [Column("Name"), Column("Note", wrap=True)]


@pytest.mark.unit
def test_pair_table_lines_maps_every_wrapped_line_to_one_row() -> None:
    """A wrapped row's physical lines all carry its id; only the first is a start."""
    rows = [_Row("r1", ["A", "alpha beta gamma delta epsilon zeta"])]
    lines, spans = render_table_blocks(_WRAP_COLUMNS, [r.cells for r in rows], max_width=22)
    assert spans[0] > 1  # the row wrapped

    paired = pair_table_lines(lines, spans, [r.item_id for r in rows])
    data = [entry for entry in paired if entry[1] == "r1"]
    assert len(data) == spans[0]  # one paired entry per physical line
    assert data[0][2] is True  # first physical line is the row start
    assert all(not entry[2] for entry in data[1:])  # continuation lines are not


@pytest.mark.unit
def test_frame_body_line_draws_caret_only_on_the_selected_row_start() -> None:
    """The caret marks the selected row's first line; continuations indent."""
    start = frame_body_line(("│ A │", "r1", True), selected_id="r1")
    cont = frame_body_line(("│ B │", "r1", False), selected_id="r1")
    other = frame_body_line(("│ C │", "r2", True), selected_id="r1")

    # Tags are stripped by the viewport; assert on the clean text.
    assert parse([start]).lines[0].startswith("> ")
    assert parse([cont]).lines[0].startswith("  ")
    assert parse([other]).lines[0].startswith("  ")
    # Both lines of the selected row are tagged for the viewport.
    assert parse([start, cont]).selected == (0, 1)


@pytest.mark.unit
def test_section_body_selected_wrapped_row_tags_its_full_span() -> None:
    """A wrapped selected row tags every physical line so ``follow`` sees it whole."""
    rows = [
        _Row("r1", ["A", "short"]),
        _Row("r2", ["B", "one two three four five six seven eight nine ten"]),
    ]
    body = section_body("Risks", _WRAP_COLUMNS, rows, width=30, empty_placeholder="(none)")
    screen = render_sectioned_screen("Stage", body, selected_id="r2")

    view = parse(screen)
    assert view.selected is not None
    start, end = view.selected
    assert end > start  # the selection spans the wrapped row's multiple lines
    # The caret sits on the first line of the selected row only.
    caret_lines = [line for line in view.lines if line.startswith("> ")]
    assert len(caret_lines) == 1


@pytest.mark.unit
def test_follow_keeps_a_tall_wrapped_selection_in_view() -> None:
    """Scrolling honours a multi-line selection's full height, not just its first line."""
    rows = [_Row(f"r{i}", [f"row{i}", "x"]) for i in range(8)]
    rows.append(_Row("tall", ["last", "alpha beta gamma delta epsilon zeta eta theta"]))
    body = section_body("Risks", _WRAP_COLUMNS, rows, width=26, empty_placeholder="(none)")
    screen = render_sectioned_screen("Stage", body, selected_id="tall")

    view = parse(screen)
    assert view.selected is not None
    start, end = view.selected
    assert end > start  # the selected row really is multi-line
    height = 12
    offset = follow(view, 0, height)
    # The whole wrapped row — first to last line — sits within the window.
    assert offset <= start
    assert end - offset < height
