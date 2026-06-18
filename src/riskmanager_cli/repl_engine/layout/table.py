"""Reusable text-UI primitives for the REPL: section rules and box tables.

These helpers are deliberately pure and presentation-only so screens can share a
single table/section style. Cells are assumed to be plain text (no ANSI escape
sequences); callers that need styling should apply it after layout.
"""

from __future__ import annotations

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
    """

    header: str
    align: HAlign = "left"
    min_width: int = _DEFAULT_MIN_WIDTH
    priority: int | None = None


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


def render_table(
    columns: list[Column], rows: list[list[str]], *, max_width: int | None = None
) -> list[str]:
    """Render *rows* as a box-drawn table with one heading per column.

    Each column is sized to the widest of its header and cells. When *max_width*
    is given and the natural table would exceed it, the least-important columns
    are first hidden (see :func:`responsive.select_columns`) until the survivors'
    minimum widths fit, then the survivors are shrunk proportionally (see
    :func:`responsive.fit_widths`) and any cell that no longer fits is elided
    with ``…``. The returned lines are, in order: the top border, the header
    row, the header separator, one line per data row, then the bottom border.
    Callers can therefore find the data-row lines at ``result[3 : 3 + len(rows)]``
    — dropping columns changes a row's content, never the row count.

    Args:
        columns: Column headers, per-column alignment, and drop priority.
        rows: Cell text per row; each row must have one cell per column.
        max_width: Maximum total columns the table box (borders, padding, and
            content) may occupy. ``None`` leaves the table at its natural size.

    Returns:
        The table's display lines.
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

    def border(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (width + 2) for width in widths) + right

    def body(cells: list[str], aligns: list[HAlign]) -> str:
        padded = (
            f" {_align(_clip(cell, widths[index]), widths[index], aligns[index])} "
            for index, cell in enumerate(cells)
        )
        return "│" + "│".join(padded) + "│"

    header_aligns: list[HAlign] = ["left"] * len(columns)
    cell_aligns: list[HAlign] = [column.align for column in columns]

    lines = [
        border("┌", "┬", "┐"),
        body([column.header for column in columns], header_aligns),
        border("├", "┼", "┤"),
    ]
    lines.extend(body(row, cell_aligns) for row in rows)
    lines.append(border("└", "┴", "┘"))
    return lines
