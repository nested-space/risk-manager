"""Reusable text-UI primitives for the REPL: section rules and box tables.

These helpers are deliberately pure and presentation-only so screens can share a
single table/section style. Cells are assumed to be plain text (no ANSI escape
sequences); callers that need styling should apply it after layout.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

from .geometry import HAlign
from .responsive import fit_widths, select_columns

# Every screen sizes its section headings through ``section_width`` so they read
# as one consistent length: a fixed column count, capped so it never dominates a
# narrow terminal.
_SECTION_WIDTH = 40
_SECTION_TERMINAL_FRACTION = 0.75

# Default floor a column is shrunk to before others give up more room, so a
# fragile narrow column (e.g. a count) is not collapsed to a sliver while a wide
# one still has slack.
_DEFAULT_MIN_WIDTH = 4


def section_width(term_width: int) -> int:
    """Return the standard section-rule width for a *term_width*-column terminal.

    The width is a fixed :data:`_SECTION_WIDTH` columns, capped at
    :data:`_SECTION_TERMINAL_FRACTION` of *term_width* so headings stay
    proportional on a narrow terminal. Always at least one column.

    Args:
        term_width: Current terminal width in columns.

    Returns:
        The shared section-heading width every screen should use.
    """
    return max(min(_SECTION_WIDTH, int(term_width * _SECTION_TERMINAL_FRACTION)), 1)


def section_rule(title: str, width: int) -> str:
    """Return a section-title rule: ``─ {title} `` padded with ``─`` to *width*.

    Args:
        title: The section heading shown inside the rule.
        width: Total visible width the rule should span.

    Returns:
        The rule line, never shorter than its ``─ {title} `` prefix.
    """
    prefix = f"─ {title} "
    return prefix + "─" * max(width - len(prefix), 0)


@dataclass
class Column:
    """One column in a box-drawn table.

    Attributes:
        header: Column heading.
        align: Cell alignment within the column.
        min_width: Width this column is shrunk no narrower than while the table
            is being fitted to a terminal, unless even the minimums cannot fit
            (see :func:`render_table`).
        priority: Drop order when the table is too narrow for every column's
            minimum width. ``None`` (the default) pins the column in place; a
            lower integer is hidden before a higher one. See
            :func:`responsive.select_columns`.
        wrap: When ``True``, an over-long cell is wrapped across multiple
            physical lines (growing the row's height) instead of being clipped
            with ``…``. The application decides which columns wrap; the engine
            owns the wrapping mechanics.
    """

    header: str
    align: HAlign = "left"
    min_width: int = _DEFAULT_MIN_WIDTH
    priority: int | None = None
    wrap: bool = False


def _align(text: str, width: int, align: HAlign) -> str:
    if align == "right":
        return text.rjust(width)
    if align == "center":
        return text.center(width)
    return text.ljust(width)


def _clip(text: str, width: int) -> str:
    """Clip *text* to *width* visible columns, eliding overflow with ``…``.

    Cells are plain text, so character count is the visible width; the ellipsis
    is a single column. Returns ``text`` unchanged when it already fits.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[: width - 1] + "…"


def _wrap_cell(text: str, width: int, wrap: bool) -> list[str]:
    """Return a cell's physical lines: wrapped when *wrap*, else clipped to one."""
    if not wrap:
        return [_clip(text, width)]
    wrapped = textwrap.wrap(text, width=max(width, 1))
    return wrapped or [""]


def _border(left: str, mid: str, right: str, widths: list[int]) -> str:
    """Return a box border (``┌┬┐``/``├┼┤``/``└┴┘``) spanning *widths*."""
    return left + mid.join("─" * (width + 2) for width in widths) + right


def _row_line(cells: list[str], widths: list[int], aligns: list[HAlign]) -> str:
    """Return one physical table line, each cell clipped, aligned, and padded.

    Clipping guards single-line cells that exceed their column width — the header
    and any non-wrap data cell. Wrapped cell lines are already within width, so
    the clip is a no-op for them.
    """
    padded = (
        f" {_align(_clip(cell, widths[index]), widths[index], aligns[index])} "
        for index, cell in enumerate(cells)
    )
    return "│" + "│".join(padded) + "│"


def _data_blocks(
    columns: list[Column], rows: list[list[str]], widths: list[int], aligns: list[HAlign]
) -> tuple[list[str], list[int]]:
    """Render the data rows, wrapping ``wrap`` columns; return lines and row spans."""
    lines: list[str] = []
    counts: list[int] = []
    for row in rows:
        wrapped = [
            _wrap_cell(cell, widths[index], columns[index].wrap) for index, cell in enumerate(row)
        ]
        height = max((len(cell) for cell in wrapped), default=1)
        for line in range(height):
            lines.append(
                _row_line(
                    [cell[line] if line < len(cell) else "" for cell in wrapped], widths, aligns
                )
            )
        counts.append(height)
    return lines, counts


def render_table_blocks(
    columns: list[Column], rows: list[list[str]], *, max_width: int | None = None
) -> tuple[list[str], list[int]]:
    """Render *rows* as a box-drawn table, reporting each row's line span.

    Behaves like :func:`render_table` for sizing and column dropping, but a row
    whose ``wrap=True`` columns overflow grows to several physical lines rather
    than being clipped. The second return value gives the number of physical
    lines each data row occupies, in row order, so selectable callers can map a
    physical line back to its logical row (see :mod:`repl.renderers._sections`).

    Args:
        columns: Column headers, per-column alignment, drop priority, and wrap.
        rows: Cell text per row; each row must have one cell per column.
        max_width: Maximum total columns the table box (borders, padding, and
            content) may occupy. ``None`` leaves the table at its natural size.

    Returns:
        ``(lines, row_line_counts)`` — the display lines (top border, header,
        separator, the data rows, bottom border) and the physical-line count of
        each data row.
    """
    if max_width is not None:
        kept = select_columns(
            [column.min_width for column in columns],
            [column.priority for column in columns],
            max_width,
        )
        columns = [columns[i] for i in kept]
        rows = [[row[i] for i in kept] for row in rows]

    widths = [len(column.header) for column in columns]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    if max_width is not None:
        # Each column costs two padding columns plus its left ``│``; one closing
        # ``│`` finishes the row, hence ``3 * n + 1`` of non-content overhead.
        budget = max_width - (3 * len(columns) + 1)
        widths = fit_widths(widths, [column.min_width for column in columns], budget)

    header_aligns: list[HAlign] = ["left"] * len(columns)
    cell_aligns: list[HAlign] = [column.align for column in columns]

    data_lines, row_line_counts = _data_blocks(columns, rows, widths, cell_aligns)
    lines = [
        _border("┌", "┬", "┐", widths),
        _row_line([column.header for column in columns], widths, header_aligns),
        _border("├", "┼", "┤", widths),
        *data_lines,
        _border("└", "┴", "┘", widths),
    ]
    return lines, row_line_counts


def render_table(
    columns: list[Column], rows: list[list[str]], *, max_width: int | None = None
) -> list[str]:
    """Render *rows* as a box-drawn table with one heading per column.

    Each column is sized to the widest of its header and cells. When *max_width*
    is given and the natural table would exceed it, the least-important columns
    are first hidden (see :func:`responsive.select_columns`) until the survivors'
    minimum widths fit, then the survivors are shrunk proportionally (see
    :func:`responsive.fit_widths`) and any cell that no longer fits is elided
    with ``…`` (or wrapped, for a ``wrap=True`` column). The returned lines are,
    in order: the top border, the header row, the header separator, the data
    rows, then the bottom border. With no wrapping each row is one line, so the
    data rows sit at ``result[3 : 3 + len(rows)]``; callers that wrap columns
    must use :func:`render_table_blocks` to recover per-row line spans.

    Args:
        columns: Column headers, per-column alignment, drop priority, and wrap.
        rows: Cell text per row; each row must have one cell per column.
        max_width: Maximum total columns the table box (borders, padding, and
            content) may occupy. ``None`` leaves the table at its natural size.

    Returns:
        The table's display lines.
    """
    lines, _ = render_table_blocks(columns, rows, max_width=max_width)
    return lines
