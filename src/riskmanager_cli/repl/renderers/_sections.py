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

from ...repl_engine.layout import Column, render_table_blocks, section_rule, section_width
from ...repl_engine.viewport import tag_selected

_BODY_INDENT = "  "
_CARET = "> "

#: A paired body line: its text, the row ``item_id`` it belongs to (``None`` for
#: borders/headers/blank lines), and whether it is the first physical line of its
#: row (where the caret is drawn).
BodyLine = tuple[str, str | None, bool]


class Row(Protocol):
    """A renderable section row: selectable when it carries an ``item_id``."""

    @property
    def item_id(self) -> str | None:
        """Caret/Enter identifier, or ``None`` for display-only rows."""

    @property
    def cells(self) -> list[str]:
        """Rendered cell text, one per column."""


def pair_table_lines(
    lines: list[str], row_line_counts: list[int], item_ids: Sequence[str | None]
) -> list[BodyLine]:
    """Pair each physical table line with its row ``item_id`` and row-start flag.

    Maps the flat output of :func:`~repl_engine.layout.render_table_blocks` back
    to logical rows: the three header lines and the bottom border carry no
    ``item_id``; every physical line of a (possibly wrapped) data row carries
    that row's ``item_id``, with ``True`` marking the row's first line.

    Args:
        lines: The table's display lines.
        row_line_counts: Physical-line count of each data row, in row order.
        item_ids: The ``item_id`` of each data row, aligned with *row_line_counts*.

    Returns:
        One :data:`BodyLine` per input line.
    """
    data_start = 3  # top border, header, separator precede the data rows
    out: list[BodyLine] = [(line, None, False) for line in lines[:data_start]]
    cursor = data_start
    for item_id, count in zip(item_ids, row_line_counts):
        for offset in range(count):
            out.append((lines[cursor + offset], item_id, offset == 0))
        cursor += count
    out.extend((line, None, False) for line in lines[cursor:])
    return out


def frame_body_line(line: BodyLine, selected_id: str | None) -> str:
    """Render one :data:`BodyLine` with its gutter, tagging the selection.

    Blank text yields an empty line. Otherwise the row is indented two columns,
    with the ``>`` caret replacing the indent on the first line of the selected
    row; every physical line of the selected row is tagged so the viewport keeps
    a wrapped row fully on screen (see :func:`repl_engine.viewport.follow`).
    """
    text, item_id, is_row_start = line
    if not text:
        return ""
    selected = item_id is not None and item_id == selected_id
    gutter = _CARET if selected and is_row_start else _BODY_INDENT
    framed = f"{gutter}{text}"
    return tag_selected([framed])[0] if selected else framed


def section_body(
    title: str,
    columns: list[Column],
    rows: Sequence[Row],
    width: int,
    empty_placeholder: str,
) -> list[BodyLine]:
    """Build :data:`BodyLine` body lines for one section.

    A blank line precedes the section rule; each physical line of the table's
    data rows carries that row's ``item_id`` (everything else is ``None``). Empty
    sections render the placeholder instead of a table. The table is shrunk to
    the terminal *width* less the screen inset and the two-column caret/indent
    gutter.
    """
    out: list[BodyLine] = [
        ("", None, False),
        (section_rule(title, section_width(width)), None, False),
        ("", None, False),
    ]
    if not rows:
        out.append((empty_placeholder, None, False))
        return out
    lines, row_line_counts = render_table_blocks(
        columns, [row.cells for row in rows], max_width=width - 4
    )
    out.extend(pair_table_lines(lines, row_line_counts, [row.item_id for row in rows]))
    return out


def render_sectioned_screen(
    title: str,
    body: list[BodyLine],
    selected_id: str | None,
) -> list[str]:
    """Frame *body* under *title*, drawing a ``>`` caret on the selected row.

    Args:
        title: Page title; rendered at column zero with an underline beneath.
        body: :data:`BodyLine` lines from :func:`section_body`.
        selected_id: ``item_id`` of the caret-selected row, if any.

    Returns:
        The full set of display lines for the page.
    """
    lines = [title, "─" * len(title)]
    lines.extend(frame_body_line(line, selected_id) for line in body)
    return lines
