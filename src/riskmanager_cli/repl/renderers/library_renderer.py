"""Render library track screens for materials, NCRM, and counterions.

Each subsection is drawn as a single box-drawn table (see ``renderers/tables.py``)
whose body is indented two columns so a ``>`` caret can occupy the left gutter on
the selected row — the same selectable-table pattern as the stage- and
component-focus screens. ``library_targets`` flattens the rows into selectable
:class:`ListItem`s for the navigator; ``render_library_screen`` draws the page for
a given selected row id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...utils.formula_parser import render_chemical_formula
from ..list_navigator import ListItem
from .tables import Column, render_table

_BODY_INDENT = "  "
_CARET = "> "

_COLUMNS = [
    Column("Name"),
    Column("Display name"),
    Column("Aliases", align="right"),
    Column("SMILES"),
]


@dataclass
class LibraryRow:
    """One selectable library row.

    Attributes:
        item_id: Library entry id, used for caret tracking and Enter routing.
        cells: Rendered cell text, one per column.
    """

    item_id: str
    cells: list[str]


def _display_cell(item: dict[str, Any]) -> str:
    """Return the display-name cell, chemically rendered when requested."""
    display = str(item.get("display_name") or item.get("name") or "")
    if item.get("interpret_chemically"):
        return render_chemical_formula(display)
    return display


def _rows(items: list[dict[str, Any]]) -> list[LibraryRow]:
    """Build the selectable rows for *items* in the order given."""
    rows: list[LibraryRow] = []
    for item in items:
        name = str(item.get("name") or item.get("display_name") or item.get("id") or "")
        smiles = str(item.get("smiles") or "")
        rows.append(
            LibraryRow(
                item_id=str(item.get("id") or ""),
                cells=[name, _display_cell(item), str(item.get("alias_count", 0)), smiles],
            )
        )
    return rows


def library_targets(items: list[dict[str, Any]]) -> list[ListItem]:
    """Flatten library items into selectable list items in render order.

    Args:
        items: Library rows already converted to dictionaries.

    Returns:
        One :class:`ListItem` per item, labelled by name and keyed by id.
    """
    return [ListItem(label=row.cells[0], item_id=row.item_id) for row in _rows(items)]


async def render_library_screen(
    sub_mode: str,
    items: list[dict[str, Any]],
    *,
    selected_id: str | None = None,
) -> list[str]:
    """Return display lines for the Library track.

    Args:
        sub_mode: Active library sub-mode (``materials``/``ncrm``/``counterions``
            or ``select`` for the subsection chooser).
        items: Library rows already converted to dictionaries, in display order.
        selected_id: ``item_id`` of the caret-selected row, if any.

    Returns:
        Renderable output lines: a title at column zero, then a two-space-indented
        table with a ``>`` caret on the selected row.
    """
    if sub_mode == "select":
        return [
            "Library",
            "",
            "Choose a subsection:",
            "  /library materials",
            "  /library ncrm",
            "  /library counterions",
        ]

    title = f"Library · {sub_mode}"
    lines = [title, ""]
    rows = _rows(items)
    if not rows:
        lines.append("(no items found)")
        return lines

    table = render_table(_COLUMNS, [row.cells for row in rows])
    data_start = 3  # top border, header, separator precede the data rows
    for index, line in enumerate(table):
        is_data = data_start <= index < data_start + len(rows)
        item_id = rows[index - data_start].item_id if is_data else None
        gutter = _CARET if item_id is not None and item_id == selected_id else _BODY_INDENT
        lines.append(f"{gutter}{line}")
    return lines
