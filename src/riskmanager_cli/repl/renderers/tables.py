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
    """

    header: str
    align: Align = "left"


def _align(text: str, width: int, align: Align) -> str:
    if align == "right":
        return text.rjust(width)
    if align == "center":
        return text.center(width)
    return text.ljust(width)


def render_table(columns: list[Column], rows: list[list[str]]) -> list[str]:
    """Render *rows* as a box-drawn table with one heading per column.

    Each column is sized to the widest of its header and cells. The returned
    lines are, in order: the top border, the header row, the header separator,
    one line per data row, then the bottom border. Callers can therefore find
    the data-row lines at ``result[3 : 3 + len(rows)]``.

    Args:
        columns: Column headers and per-column alignment.
        rows: Cell text per row; each row must have one cell per column.

    Returns:
        The table's display lines.
    """
    widths = [len(column.header) for column in columns]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def border(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (width + 2) for width in widths) + right

    def body(cells: list[str], aligns: list[Align]) -> str:
        padded = (
            f" {_align(cell, widths[index], aligns[index])} " for index, cell in enumerate(cells)
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
