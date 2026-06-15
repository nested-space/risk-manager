"""Pin box-table headers to the top of the output pane while scrolling.

The output pane renders a flat ``list[str]`` and is scrolled by slicing it (see
``screen.ScreenManager.draw_output``). A long table therefore scrolls its column
headings off the top, leaving data rows unlabelled. These pure helpers re-insert
a table's 3-line header block whenever the scroll position has pushed it off but
data rows are still visible — the data rows below simply slide under the pinned
header (the topmost ones are hidden, which keeps every line reachable as you
scroll).

Tables are detected structurally: only :func:`~.renderers.tables.render_table`
emits a ``├…┼…┤`` separator as the third line of a ``┌…┐`` block, so a box frame
(``renderers/box.py``, corners only) is never mistaken for a table. Header,
separator, and border lines only ever carry a space-only gutter (the ``"> "``
caret appears solely on data rows), so ``lstrip(" ")`` safely normalises a line
before matching.
"""

from __future__ import annotations

from dataclasses import dataclass

_HEADER_LINES = 3  # top border, header row, separator


@dataclass(frozen=True)
class TableSpan:
    """The line-index extent of one box-drawn table within an output buffer.

    Attributes:
        top: Index of the ``┌`` top-border line.
        first_data: Index of the first data row (``top + 3``).
        last_data: Index of the last data row (``bottom - 1``).
        bottom: Index of the ``└`` bottom-border line.
    """

    top: int
    first_data: int
    last_data: int
    bottom: int


def index_tables(lines: list[str]) -> list[TableSpan]:
    """Locate every box-drawn table in *lines*.

    A span starts where a line strips to ``┌`` and the line two below strips to
    ``├`` (the header separator, unique to tables), and ends at the next line
    that strips to ``└``.

    Args:
        lines: The full output buffer.

    Returns:
        One :class:`TableSpan` per table, in top-to-bottom order. Tables with no
        data rows are still reported (``first_data > last_data``).
    """
    spans: list[TableSpan] = []
    total = len(lines)
    index = 0
    while index < total:
        if _strip(lines[index]).startswith("┌") and _is_separator(lines, index + 2):
            bottom = _find_bottom(lines, index + 2)
            if bottom is not None:
                spans.append(
                    TableSpan(
                        top=index,
                        first_data=index + _HEADER_LINES,
                        last_data=bottom - 1,
                        bottom=bottom,
                    )
                )
                index = bottom + 1
                continue
        index += 1
    return spans


def pinned_window(lines: list[str], offset: int, height: int) -> list[str]:
    """Return the *height* lines to draw at *offset*, pinning any table header.

    When *offset* sits within a table's body (its top border already scrolled
    off, data rows still showing), the table's 3-line header is prepended and the
    body is taken from ``offset + 3`` so the result stays *height* lines tall —
    the topmost data rows slide under the pinned header. Otherwise the plain
    ``lines[offset : offset + height]`` slice is returned unchanged.

    Args:
        lines: The full output buffer.
        offset: Index of the first line that would be shown without pinning.
        height: Number of pane rows available.

    Returns:
        The lines to draw, at most *height* long.
    """
    if height > _HEADER_LINES:
        for span in index_tables(lines):
            if span.top < offset <= span.last_data:
                header = lines[span.top : span.top + _HEADER_LINES]
                body = lines[offset + _HEADER_LINES : offset + height]
                return header + body
    return lines[offset : offset + height]


def reserved_top(lines: list[str], line_index: int) -> int:
    """Rows a pinned header would hide above *line_index*, or ``0``.

    Returns :data:`_HEADER_LINES` when *line_index* is a data row of some table
    (its header pins once scrolled into), so caret-follow can keep a selected row
    clear of the pinned band; ``0`` otherwise.

    Args:
        lines: The full output buffer.
        line_index: Index of the line of interest (typically the selected row).

    Returns:
        ``3`` inside a table body, else ``0``.
    """
    for span in index_tables(lines):
        if span.first_data <= line_index <= span.last_data:
            return _HEADER_LINES
    return 0


def _strip(line: str) -> str:
    """Drop the space-only gutter so a border line can be matched by its corner."""
    return line.lstrip(" ")


def _is_separator(lines: list[str], index: int) -> bool:
    """Return whether *lines[index]* exists and strips to a ``├`` separator."""
    return 0 <= index < len(lines) and _strip(lines[index]).startswith("├")


def _find_bottom(lines: list[str], start: int) -> int | None:
    """Return the index of the next ``└`` bottom border after *start*, if any."""
    for index in range(start + 1, len(lines)):
        if _strip(lines[index]).startswith("└"):
            return index
    return None
