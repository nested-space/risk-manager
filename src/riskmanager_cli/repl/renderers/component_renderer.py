"""Component-focus screen rendering as a sectioned, navigable page.

Renders a single component in the same style as the Stage Focus screen (see
``renderers/stage_renderer.py``): a component title followed by three sections —
``Details``, ``Salts``, and ``Risks`` — each a section-title rule above a
box-drawn table (see ``renderers/tables.py``). The whole body is indented two
columns so a ``>`` caret can occupy the left gutter.

``Details`` rows are display-only; ``Salts`` and ``Risks`` rows are selectable so
the caret can walk them (Enter opens the component-risk edit form for a risk and
is a no-op for a salt; ``^U`` unassigns either). ``gather_component_sections``
fetches the rows once; ``component_targets`` flattens the selectable ones into
:class:`ListItem`s for the navigator; ``render_component_screen`` draws the page
for a given selected row id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from ...config.settings import Environment
from ...model.severity import format_level
from ...model.tables import Component, Material
from ...operations.component_risks_operations import list_risks_for_component
from ...operations.component_salt_operations import list_salts_for_component
from ...operations.counterion_operations import get_counterion_by_id
from ..list_navigator import ListItem
from .tables import Column, render_table, section_rule, section_width

_BODY_INDENT = "  "
_CARET = "> "


@dataclass
class ComponentRow:
    """One row in a component section.

    Attributes:
        item_id: ``"{kind}:{uuid}"`` identifier used for caret tracking and
            Enter routing, or ``None`` for display-only rows.
        cells: Rendered cell text, one per column.
    """

    item_id: str | None
    cells: list[str]


@dataclass
class ComponentSections:
    """The three component sections, each a list of rows."""

    details: list[ComponentRow] = field(default_factory=list)
    salts: list[ComponentRow] = field(default_factory=list)
    risks: list[ComponentRow] = field(default_factory=list)


_DETAIL_COLUMNS = [Column("Property"), Column("Value")]
_SALT_COLUMNS = [
    Column("Counterion"),
    Column("Stoichiometry", align="right"),
    Column("Defined", align="center"),
]
_RISK_COLUMNS = [
    Column("Type"),
    Column("Name"),
    Column("Level", align="center"),
    Column("Mitigated", align="center"),
]


async def gather_component_sections(
    component: Component, material: Material | None, env: Environment
) -> ComponentSections:
    """Fetch the component's details, salts, and risks as renderable rows."""
    return ComponentSections(
        details=_detail_rows(component, material),
        salts=await _salt_rows(component, env),
        risks=await _risk_rows(component, env),
    )


def component_targets(sections: ComponentSections) -> list[ListItem]:
    """Flatten the selectable rows into list items in render order.

    Salt and risk rows are selectable (so they can be unassigned with ``^U``);
    detail rows stay display-only. Salts precede risks to match render order. The
    label is the row's name column — the counterion for salts, the risk name for
    risks.
    """
    salts = [
        ListItem(label=row.cells[0], item_id=row.item_id)
        for row in sections.salts
        if row.item_id is not None
    ]
    risks = [
        ListItem(label=row.cells[1], item_id=row.item_id)
        for row in sections.risks
        if row.item_id is not None
    ]
    return [*salts, *risks]


def render_component_screen(
    sections: ComponentSections,
    *,
    display_name: str,
    width: int = 80,
    selected_id: str | None = None,
) -> list[str]:
    """Return display lines for the Component Focus page.

    Args:
        sections: Pre-fetched section rows (see :func:`gather_component_sections`).
        display_name: The component's salt-form name (see
            :func:`~...operations.component_operations.component_display_name`),
            used for the title.
        width: Terminal width; section rules use the shared standard width.
        selected_id: ``item_id`` of the caret-selected row, if any.

    Returns:
        Renderable lines: a component title and underline at column zero, then
        the two-space-indented sections with a ``>`` caret on the selected row.
    """
    title = f"Component: {display_name}"
    lines = [title, "─" * len(title)]

    body_width = section_width(width)
    body: list[tuple[str, str | None]] = []
    body += _section_body("Details", _DETAIL_COLUMNS, sections.details, body_width, "(none)")
    body += _section_body("Salts", _SALT_COLUMNS, sections.salts, body_width, "(no salts)")
    body += _section_body("Risks", _RISK_COLUMNS, sections.risks, body_width, "(no risks recorded)")

    for text, item_id in body:
        if not text:
            lines.append("")
            continue
        gutter = _CARET if item_id is not None and item_id == selected_id else _BODY_INDENT
        lines.append(f"{gutter}{text}")
    return lines


def _section_body(
    title: str,
    columns: list[Column],
    rows: list[ComponentRow],
    body_width: int,
    empty_placeholder: str,
) -> list[tuple[str, str | None]]:
    """Build ``(text, item_id)`` body lines for one section.

    A blank line precedes the section rule; the table's data rows carry their
    row ``item_id`` (everything else is ``None``). Empty sections render the
    placeholder instead of a table.
    """
    out: list[tuple[str, str | None]] = [
        ("", None),
        (section_rule(title, body_width), None),
        ("", None),
    ]
    if not rows:
        out.append((empty_placeholder, None))
        return out
    table = render_table(columns, [row.cells for row in rows])
    data_start = 3  # top border, header, separator precede the data rows
    for index, line in enumerate(table):
        is_data = data_start <= index < data_start + len(rows)
        out.append((line, rows[index - data_start].item_id if is_data else None))
    return out


def _detail_rows(component: Component, material: Material | None) -> list[ComponentRow]:
    """Return the display-only property/value rows for the component."""
    rows = [
        ComponentRow(None, ["Material", material.name if material is not None else "-"]),
        ComponentRow(None, ["Control role", component.control_strategy_role or "-"]),
        ComponentRow(None, ["Isolated", "yes" if component.is_isolated else "no"]),
    ]
    if material is not None and material.smiles:
        rows.append(ComponentRow(None, ["SMILES", material.smiles]))
    return rows


async def _salt_rows(component: Component, env: Environment) -> list[ComponentRow]:
    """Return selectable salt rows (counterion, stoichiometry, defined)."""
    salts = await list_salts_for_component(UUID(str(component.id)), env)
    rows: list[ComponentRow] = []
    for salt in salts:
        name = str(salt.counterion_id)
        counterion = await get_counterion_by_id(UUID(str(salt.counterion_id)), env)
        if counterion is not None:
            name = counterion.name
        stoichiometry = "-" if salt.stoichiometry is None else f"{salt.stoichiometry:g}"
        if salt.is_fully_defined is None:
            defined = "-"
        else:
            defined = "yes" if salt.is_fully_defined else "no"
        rows.append(ComponentRow(f"salt:{salt.id}", [name, stoichiometry, defined]))
    return rows


async def _risk_rows(component: Component, env: Environment) -> list[ComponentRow]:
    """Return selectable risk rows (type, name, level, mitigated level)."""
    risks = await list_risks_for_component(UUID(str(component.id)), env)
    return [
        ComponentRow(
            item_id=f"risk:{risk.id}",
            cells=[
                risk.risk_type,
                risk.name,
                format_level(risk.current_level),
                format_level(risk.mitigated_level),
            ],
        )
        for risk in risks
    ]
