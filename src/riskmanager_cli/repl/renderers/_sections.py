"""Shared layout for sectioned, navigable focus screens.

The Stage Focus and Component Focus screens render identically: a title and
underline at column zero, then a sequence of sections (a section rule above a
box-drawn table), with the whole body indented two columns so a ``>`` caret can
occupy the left gutter on the selected row. This module owns that shared shape so
:mod:`.stage_renderer` and :mod:`.component_renderer` only describe their own
rows, columns, and titles.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ...repl_engine.layout import Column, render_table, section_rule, section_width

_BODY_INDENT = "  "
_CARET = "> "


class Row(Protocol):
    """A renderable section row: selectable when it carries an ``item_id``."""

    @property
    def item_id(self) -> str | None:
        """Caret/Enter identifier, or ``None`` for display-only rows."""

    @property
    def cells(self) -> list[str]:
        """Rendered cell text, one per column."""


def section_body(
    title: str,
    columns: list[Column],
    rows: Sequence[Row],
    width: int,
    empty_placeholder: str,
) -> list[tuple[str, str | None]]:
    """Build ``(text, item_id)`` body lines for one section.

    A blank line precedes the section rule; the table's data rows carry their
    row ``item_id`` (everything else is ``None``). Empty sections render the
    placeholder instead of a table. The table is shrunk to the terminal *width*
    less the screen inset and the two-column caret/indent gutter.
    """
    out: list[tuple[str, str | None]] = [
        ("", None),
        (section_rule(title, section_width(width)), None),
        ("", None),
    ]
    if not rows:
        out.append((empty_placeholder, None))
        return out
    table = render_table(columns, [row.cells for row in rows], max_width=width - 4)
    data_start = 3  # top border, header, separator precede the data rows
    for index, line in enumerate(table):
        is_data = data_start <= index < data_start + len(rows)
        out.append((line, rows[index - data_start].item_id if is_data else None))
    return out


def render_sectioned_screen(
    title: str,
    body: list[tuple[str, str | None]],
    selected_id: str | None,
) -> list[str]:
    """Frame *body* under *title*, drawing a ``>`` caret on the selected row.

    Args:
        title: Page title; rendered at column zero with an underline beneath.
        body: ``(text, item_id)`` lines from :func:`section_body`. Blank text
            renders an empty line; otherwise the row is indented two columns,
            with the caret replacing the indent when ``item_id == selected_id``.
        selected_id: ``item_id`` of the caret-selected row, if any.

    Returns:
        The full set of display lines for the page.
    """
    lines = [title, "─" * len(title)]
    for text, item_id in body:
        if not text:
            lines.append("")
            continue
        gutter = _CARET if item_id is not None and item_id == selected_id else _BODY_INDENT
        lines.append(f"{gutter}{text}")
    return lines
