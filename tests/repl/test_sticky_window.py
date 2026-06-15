"""Unit tests for the sticky table-header windowing helpers."""

import pytest

from riskmanager_cli.repl.renderers.box import render_box
from riskmanager_cli.repl.renderers.tables import Column, render_table
from riskmanager_cli.repl.sticky_window import index_tables, pinned_window, reserved_top


def _table_lines(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a table behind the two-space body gutter the screens apply."""
    table = render_table([Column(header) for header in headers], rows)
    return [f"  {line}" for line in table]


def _sample() -> list[str]:
    """A title, a blank, then a gutter-indented eight-row table."""
    rows = [[chr(ord("A") + index), "role"] for index in range(8)]
    return ["Library · materials", "", *_table_lines(["Name", "Role"], rows)]


@pytest.mark.unit
def test_index_tables_locates_the_table_extent() -> None:
    """A single table is found with correct border and data-row indices."""
    lines = _sample()
    spans = index_tables(lines)
    assert len(spans) == 1
    span = spans[0]
    assert lines[span.top].lstrip().startswith("┌")
    assert lines[span.bottom].lstrip().startswith("└")
    assert span.first_data == span.top + 3
    assert span.last_data == span.bottom - 1
    assert span.last_data - span.first_data + 1 == 8  # eight data rows


@pytest.mark.unit
def test_index_tables_ignores_a_box_frame() -> None:
    """A ``render_box`` frame has no ``├`` separator and is not a table."""
    assert index_tables(render_box(["hello", "world"], 20)) == []


@pytest.mark.unit
def test_index_tables_finds_stacked_tables() -> None:
    """Two tables in one buffer are reported as two separate spans."""
    lines = [
        *_table_lines(["A"], [["1"], ["2"]]),
        "",
        *_table_lines(["B"], [["3"], ["4"]]),
    ]
    assert len(index_tables(lines)) == 2


@pytest.mark.unit
def test_pinned_window_prepends_header_inside_body() -> None:
    """Scrolled into the body, the 3-line header is pinned above the rows."""
    lines = _sample()
    span = index_tables(lines)[0]
    header = lines[span.top : span.top + 3]
    height = 6
    window = pinned_window(lines, span.first_data, height)
    assert len(window) == height
    assert window[:3] == header
    # The body resumes three lines on, so the rows slide under the header.
    assert window[3] == lines[span.first_data + 3]


@pytest.mark.unit
def test_pinned_window_is_a_plain_slice_above_the_table() -> None:
    """With the top border on screen the header shows naturally — no pinning."""
    lines = _sample()
    span = index_tables(lines)[0]
    window = pinned_window(lines, span.top, 6)
    assert window == lines[span.top : span.top + 6]


@pytest.mark.unit
def test_pinned_window_is_a_plain_slice_below_the_table() -> None:
    """Once scrolled past the last data row, nothing is pinned."""
    lines = _sample()
    span = index_tables(lines)[0]
    window = pinned_window(lines, span.bottom, 6)
    assert window == lines[span.bottom : span.bottom + 6]


@pytest.mark.unit
def test_reserved_top_is_three_inside_a_body_and_zero_elsewhere() -> None:
    """Reserved rows apply to data rows only, not borders or surrounding text."""
    lines = _sample()
    span = index_tables(lines)[0]
    assert reserved_top(lines, span.first_data) == 3
    assert reserved_top(lines, span.last_data) == 3
    assert reserved_top(lines, span.top) == 0
    assert reserved_top(lines, span.bottom) == 0
    assert reserved_top(lines, 0) == 0
