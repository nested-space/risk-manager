"""Component-focus screen rendering as a sectioned, navigable page.

Renders a single component in the same style as the Stage Focus screen (see
``renderers/stage_renderer.py``): a component title followed by three sections —
``Details``, ``Salts``, and ``Risks`` — each a section-title rule above a
box-drawn table (see ``renderers/layout/table.py``). The whole body is indented two
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
from ...repl_engine.layout import Column
from ...repl_engine.list_navigator import ListItem
from ._sections import BodyLine, render_sectioned_screen, section_body


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
    Column("Stoichiometry", align="right", priority=1),
    Column("Defined", align="center", priority=0),
]
_RISK_COLUMNS = [
    Column("Type", priority=1),
    Column("Name", wrap=True),
    Column("Level", align="center", priority=2),
    Column("Mitigated", align="center", priority=0),
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
    body: list[BodyLine] = []
    body += section_body("Details", _DETAIL_COLUMNS, sections.details, width, "(none)")
    body += section_body("Salts", _SALT_COLUMNS, sections.salts, width, "(no salts)")
    body += section_body("Risks", _RISK_COLUMNS, sections.risks, width, "(no risks recorded)")
    return render_sectioned_screen(title, body, selected_id)


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
