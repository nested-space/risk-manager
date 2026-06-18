"""Render library track screens for materials, NCRM, and counterions.

Each subsection is drawn as a single box-drawn table (see ``renderers/layout/table.py``)
whose body is indented two columns so a ``>`` caret can occupy the left gutter on
the selected row — the same selectable-table pattern as the stage- and
component-focus screens. ``library_targets`` flattens the rows into selectable
:class:`ListItem`s for the navigator; ``render_library_screen`` draws the page for
a given selected row id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...repl_engine.layout import Column, render_table, section_rule, section_width
from ...repl_engine.list_navigator import ListItem
from ...utils.formula_parser import render_chemical_formula

_BODY_INDENT = "  "
_CARET = "> "

# Name is the identity column and stays; the rest drop on a narrow terminal,
# SMILES first, then the display name, leaving the alias count longest.
_COLUMNS = [
    Column("Name"),
    Column("Display name", priority=1),
    Column("Aliases", align="right", min_width=3, priority=2),
    Column("SMILES", priority=0),
]

_DETAIL_COLUMNS = [Column("Property"), Column("Value")]


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
    width: int = 80,
    selected_id: str | None = None,
) -> list[str]:
    """Return display lines for the Library track.

    Args:
        sub_mode: Active library sub-mode (``materials``/``ncrm``/``counterions``).
            The ``select`` landing page is rendered separately by
            :func:`library_home_renderer.render_library_home`.
        items: Library rows already converted to dictionaries, in display order.
        width: Terminal width; the table is shrunk to fit it.
        selected_id: ``item_id`` of the caret-selected row, if any.

    Returns:
        Renderable output lines: a title at column zero, then a two-space-indented
        table with a ``>`` caret on the selected row.
    """
    title = f"Library · {sub_mode}"
    lines = [title, ""]
    rows = _rows(items)
    if not rows:
        lines.append("(no items found)")
        return lines

    # Two columns are lost to the screen inset and two to the caret/indent gutter.
    table = render_table(_COLUMNS, [row.cells for row in rows], max_width=width - 4)
    data_start = 3  # top border, header, separator precede the data rows
    for index, line in enumerate(table):
        is_data = data_start <= index < data_start + len(rows)
        item_id = rows[index - data_start].item_id if is_data else None
        gutter = _CARET if item_id is not None and item_id == selected_id else _BODY_INDENT
        lines.append(f"{gutter}{line}")
    return lines


def render_library_detail(
    item: dict[str, Any],
    aliases: list[str],
    *,
    width: int = 80,
) -> list[str]:
    """Return display lines for a single library entry's detail (show) page.

    Drawn in the same sectioned style as the component- and stage-focus screens:
    an entry title with an underline, a box-drawn ``Details`` table, and an
    ``Aliases`` section rendered as a simple bulleted list.

    Args:
        item: The resolved library row dict (``id``/``name``/``display_name``/
            ``interpret_chemically``/``smiles``/``alias_count``).
        aliases: The entry's aliases, already in display order.
        width: Terminal width; the table and section rules are sized to fit it.

    Returns:
        Renderable lines: the entry name and underline at column zero, then a
        two-space-indented ``Details`` table and an ``Aliases`` list.
    """
    name = str(item.get("name") or item.get("display_name") or item.get("id") or "")
    lines = [name, "─" * len(name)]

    detail_rows = [
        ["Name", name],
        ["Display name", _display_cell(item)],
        ["Interpret chemically", "yes" if item.get("interpret_chemically") else "no"],
        ["SMILES", str(item.get("smiles") or "-")],
    ]
    lines += ["", section_rule("Details", section_width(width)), ""]
    lines += [
        f"{_BODY_INDENT}{line}"
        for line in render_table(_DETAIL_COLUMNS, detail_rows, max_width=width - 4)
    ]

    lines += ["", section_rule(f"Aliases ({len(aliases)})", section_width(width)), ""]
    if aliases:
        lines += [f"{_BODY_INDENT}• {alias}" for alias in aliases]
    else:
        lines.append(f"{_BODY_INDENT}(no aliases)")
    return lines
