"""Stage-focus screen rendering as a sectioned, navigable page.

Renders a single stage as a stage title followed by three sections —
``Components``, ``NCRMs``, and ``Risks`` — each a section-title rule above a
box-drawn table (see ``renderers/layout/table.py``). The whole body is indented two
columns so a ``>`` caret can occupy the left gutter; a single unified selection
moves through every data row across the three tables in render order.

``gather_stage_sections`` fetches the rows once; ``stage_targets`` flattens them
into selectable :class:`ListItem`s for the navigator; ``render_stage_screen``
draws the page for a given selected row id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from ...config.settings import Environment
from ...model.severity import format_level
from ...model.tables import Stage
from ...operations.component_operations import component_display_name, get_component_by_id
from ...operations.ncrm_library_operations import get_ncrm_by_id
from ...operations.stage_component_operations import list_stage_components
from ...operations.stage_ncrm_operations import list_ncrms_for_stage
from ...operations.stage_risk_operations import list_risks_for_stage
from ...repl_engine.layout import Column, render_table, section_rule, section_width
from ...repl_engine.list_navigator import ListItem

_BODY_INDENT = "  "
_CARET = "> "


@dataclass
class StageRow:
    """One selectable data row in a stage section.

    Attributes:
        item_id: ``"{kind}:{uuid}"`` identifier (``component`` / ``ncrm`` /
            ``risk``) used for caret tracking and Enter routing.
        cells: Rendered cell text, one per column.
    """

    item_id: str
    cells: list[str]


@dataclass
class StageSections:
    """The three stage sections, each a list of selectable rows."""

    components: list[StageRow] = field(default_factory=list)
    ncrms: list[StageRow] = field(default_factory=list)
    risks: list[StageRow] = field(default_factory=list)


_COMPONENT_COLUMNS = [Column("Name"), Column("Role", priority=0)]
_NCRM_COLUMNS = [Column("Name"), Column("Role", priority=0)]
_RISK_COLUMNS = [
    Column("Name"),
    Column("Description", priority=0),
    Column("Level", align="center", priority=3),
    Column("Mitigation", priority=1),
    Column("Mitigated level", align="center", priority=2),
]


async def gather_stage_sections(stage: Stage, env: Environment) -> StageSections:
    """Fetch the stage's components, NCRMs, and risks as renderable rows."""
    return StageSections(
        components=await _component_rows(stage, env),
        ncrms=await _ncrm_rows(stage, env),
        risks=await _risk_rows(stage, env),
    )


def stage_targets(sections: StageSections) -> list[ListItem]:
    """Flatten the sections into selectable list items in render order."""
    rows = [*sections.components, *sections.ncrms, *sections.risks]
    return [ListItem(label=row.cells[0], item_id=row.item_id) for row in rows]


def render_stage_screen(
    stage: Stage,
    sections: StageSections,
    *,
    width: int = 80,
    selected_id: str | None = None,
) -> list[str]:
    """Return display lines for the Stage Focus page.

    Args:
        stage: Stage being rendered.
        sections: Pre-fetched section rows (see :func:`gather_stage_sections`).
        width: Terminal width; section rules use the shared standard width.
        selected_id: ``item_id`` of the caret-selected row, if any.

    Returns:
        Renderable lines: a stage title and underline at column zero, then the
        two-space-indented sections with a ``>`` caret on the selected row.
    """
    title = f"Stage {stage.number}"
    lines = [title, "─" * len(title)]

    body: list[tuple[str, str | None]] = []
    body += _section_body("Components", _COMPONENT_COLUMNS, sections.components, width, "(none)")
    body += _section_body("NCRMs", _NCRM_COLUMNS, sections.ncrms, width, "(none)")
    body += _section_body("Risks", _RISK_COLUMNS, sections.risks, width, "(no risks recorded)")

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
    rows: list[StageRow],
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


async def _component_rows(stage: Stage, env: Environment) -> list[StageRow]:
    """Return component rows (name, role), reactants sorted ahead of products."""
    links = await list_stage_components(UUID(str(stage.id)), env)
    rows: list[tuple[str, StageRow]] = []
    for link in links:
        name = str(link.component_id)
        component = await get_component_by_id(UUID(str(link.component_id)), env)
        if component is not None:
            name = await component_display_name(component, env)
        rows.append(
            (
                link.component_type,
                StageRow(
                    item_id=f"component:{link.component_id}",
                    cells=[name, link.component_type.title()],
                ),
            )
        )
    rows.sort(key=lambda item: 0 if item[0] == "reactant" else 1)
    return [row for _, row in rows]


async def _ncrm_rows(stage: Stage, env: Environment) -> list[StageRow]:
    """Return NCRM rows (name, role) for the stage's NCRM links."""
    links = await list_ncrms_for_stage(UUID(str(stage.id)), env)
    rows: list[StageRow] = []
    for link in links:
        name = str(link.ncrm_id)
        ncrm = await get_ncrm_by_id(UUID(str(link.ncrm_id)), env)
        if ncrm is not None:
            name = ncrm.display_name
        rows.append(StageRow(item_id=f"ncrm:{link.id}", cells=[name, link.role.value.title()]))
    return rows


async def _risk_rows(stage: Stage, env: Environment) -> list[StageRow]:
    """Return risk rows (name, description, level, mitigation, mitigated level)."""
    risks = await list_risks_for_stage(UUID(str(stage.id)), env)
    return [
        StageRow(
            item_id=f"risk:{risk.id}",
            cells=[
                risk.name,
                risk.description or "",
                _level(risk.current_level),
                risk.proposed_mitigation or "",
                _level(risk.mitigated_level),
            ],
        )
        for risk in risks
    ]


def _level(value: int | None) -> str:
    return format_level(value)
