"""Reusable text-UI primitives for the REPL: section rules and box tables.

These helpers are deliberately pure and presentation-only so screens can share a
single table/section style. Cells are assumed to be plain text (no ANSI escape
sequences); callers that need styling should apply it after layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Align = Literal["left", "center", "right"]

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
    """

    header: str
    align: Align = "left"
    min_width: int = _DEFAULT_MIN_WIDTH


def _align(text: str, width: int, align: Align) -> str:
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


def _fit_widths(natural: list[int], minimums: list[int], budget: int) -> list[int]:
    """Shrink *natural* column widths so their sum fits *budget*.

    Reduction is shared across columns in proportion to each column's slack
    (``natural - floor``), so wide columns give up room before narrow ones reach
    their floor.

    Args:
        natural: Each column's content-sized width.
        minimums: Each column's preferred floor (``Column.min_width``).
        budget: Total content columns available (table width minus borders and
            padding).

    Returns:
        The fitted per-column widths, summing to at most ``budget`` whenever that
        is achievable without collapsing a column below its floor.

    Why this exists:
        When every minimum cannot be honoured (``sum(minimums) > budget``) the
        floors are dropped to a single column each, so the table shrinks evenly
        rather than letting one fragile column be erased.
    """
    if sum(natural) <= budget:
        return list(natural)
    floors = [min(m, n) for m, n in zip(minimums, natural, strict=True)]
    if sum(floors) > budget:
        floors = [min(1, n) for n in natural]
    slack = [n - f for n, f in zip(natural, floors, strict=True)]
    total_slack = sum(slack)
    if total_slack <= 0:
        return floors
    excess = sum(natural) - budget
    widths = list(natural)
    removed = 0
    for index, give in enumerate(slack):
        take = give * excess // total_slack
        widths[index] -= take
        removed += take
    # Largest-remainder rounding can leave a few columns over budget; trim the
    # shortfall from any column that still sits above its floor.
    index = 0
    while removed < excess:
        if widths[index] > floors[index]:
            widths[index] -= 1
            removed += 1
        index = (index + 1) % len(widths)
    return widths


def render_table(
    columns: list[Column], rows: list[list[str]], *, max_width: int | None = None
) -> list[str]:
    """Render *rows* as a box-drawn table with one heading per column.

    Each column is sized to the widest of its header and cells. When *max_width*
    is given and the natural table would exceed it, columns are shrunk
    proportionally (see :func:`_fit_widths`) and any cell that no longer fits is
    elided with ``…``. The returned lines are, in order: the top border, the
    header row, the header separator, one line per data row, then the bottom
    border. Callers can therefore find the data-row lines at
    ``result[3 : 3 + len(rows)]``.

    Args:
        columns: Column headers and per-column alignment.
        rows: Cell text per row; each row must have one cell per column.
        max_width: Maximum total columns the table box (borders, padding, and
            content) may occupy. ``None`` leaves the table at its natural size.

    Returns:
        The table's display lines.
    """
    widths = [len(column.header) for column in columns]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    if max_width is not None:
        # Each column costs two padding columns plus its left ``│``; one closing
        # ``│`` finishes the row, hence ``3 * n + 1`` of non-content overhead.
        budget = max_width - (3 * len(columns) + 1)
        widths = _fit_widths(widths, [column.min_width for column in columns], budget)

    def border(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (width + 2) for width in widths) + right

    def body(cells: list[str], aligns: list[Align]) -> str:
        padded = (
            f" {_align(_clip(cell, widths[index]), widths[index], aligns[index])} "
            for index, cell in enumerate(cells)
        )
        return "│" + "│".join(padded) + "│"

    header_aligns: list[Align] = ["left"] * len(columns)
    cell_aligns: list[Align] = [column.align for column in columns]

    lines = [
        border("┌", "┬", "┐"),
        body([column.header for column in columns], header_aligns),
        border("├", "┼", "┤"),
    ]
    lines.extend(body(row, cell_aligns) for row in rows)
    lines.append(border("└", "┴", "┘"))
    return lines
