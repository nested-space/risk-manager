"""Route-screen rendering helpers."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from ...config.settings import Environment
from ...model.severity import format_level
from ...model.tables import ManufacturingProcess
from ...operations.visualization_operations import (
    AggregatedRouteRisk,
    get_aggregated_route_risks,
    get_graph_inputs,
    get_unconnected_component_names,
)
from ...repl_engine.layout import Column, render_box, render_table, section_rule, section_width
from ...utils.component_graph_layout import (
    ComponentInput,
    IncompleteProcessError,
    StageInput,
    split_for_width,
)

# Box chrome consumed before the graph: two reserved screen margins, two box
# borders, and ``2 * _PAD_X`` interior padding columns.
_PAD_X = 2
_PAD_Y = 2
_RESERVED = 2

# Aggregated-risk table columns. ``Title`` is pinned (no priority); the rest drop
# from least to most important as the terminal narrows, keeping source, title,
# and level legible longest.
_RISK_COLUMNS = [
    Column("Component/Stage", priority=4),
    Column("Entity name", priority=5),
    Column("Type", priority=1),
    Column("Level", align="center", priority=3),
    Column("Title", wrap=True),
    Column("Mitigation", priority=0, wrap=True),
    Column("Mitigated level", align="center", priority=2),
]


def _identity(text: str) -> str:
    return text


async def render_route_screen(
    process: ManufacturingProcess,
    env: Environment,
    *,
    width: int = 80,
    dim: Callable[[str], str] = _identity,
) -> list[str]:
    """Return display lines for Route View.

    Args:
        process: Manufacturing process to render.
        env: Active database environment.
        width: Terminal width; the component graph splits into stacked
            ``Route To X:`` sub-graphs when it would exceed this.
        dim: Styling function for greyed text (stage labels, section headers).

    Returns:
        Renderable output lines.
    """
    box_width = max(width - _RESERVED, 0)
    diagram_lines = await _diagram_lines(process, env, width, dim)
    boxed_diagram = render_box(diagram_lines, box_width, pad_x=_PAD_X, pad_y=_PAD_Y)

    unconnected = await get_unconnected_component_names(UUID(str(process.id)), env)
    warning_lines: list[str] = []
    if unconnected:
        warning_lines = [
            "",
            "⚠ Components not in process graph:",
            *[f"  • {name}" for name in unconnected],
        ]

    rule_width = section_width(width)
    process_title = f"Route {process.route_number} Process {process.process_number}"
    return [
        section_rule(process_title, rule_width),
        "",
        *boxed_diagram,
        *warning_lines,
        "",
        section_rule("Risks", rule_width),
        "",
        *await _risk_table(process, env, box_width),
    ]


async def _risk_table(process: ManufacturingProcess, env: Environment, max_width: int) -> list[str]:
    """Render every route risk (stage, component, process) as one table.

    Falls back to a ``(no risks recorded)`` placeholder when the route has no
    risks, so the section never renders an empty table frame.
    """
    risks = await get_aggregated_route_risks(UUID(str(process.id)), env)
    if not risks:
        return ["  (no risks recorded)"]
    rows = [_risk_row(risk) for risk in risks]
    return render_table(_RISK_COLUMNS, rows, max_width=max_width)


def _risk_row(risk: AggregatedRouteRisk) -> list[str]:
    """Map an aggregated risk to a cell list matching ``_RISK_COLUMNS``."""
    return [
        risk.source,
        risk.entity_name,
        risk.risk_type,
        format_level(risk.current_level),
        risk.name,
        risk.proposed_mitigation or "",
        format_level(risk.mitigated_level),
    ]


async def _diagram_lines(
    process: ManufacturingProcess,
    env: Environment,
    width: int,
    dim: Callable[[str], str],
) -> list[str]:
    """Return the component-graph lines, or the linear stage fallback.

    Splits a wide graph into stacked ``Route To X:`` sections; falls back to the
    linear stage strip when the graph is incomplete or invalid (still being
    built) so the route view stays usable at every step.
    """
    # Reserve the box chrome (margins, borders, interior padding) so the graph
    # never overflows the box; only break into sub-graphs once it exceeds the
    # padded interior.
    graph_budget = max(width - _RESERVED - 2 - 2 * _PAD_X, 1)
    inputs = await get_graph_inputs(UUID(str(process.id)), env)
    if inputs is not None:
        stages, components = inputs
        try:
            return _assemble_sections(split_for_width(stages, components, graph_budget, dim), dim)
        except IncompleteProcessError:
            return [
                "(process graph incomplete — showing stage list)",
                "",
                *_stage_list_lines(stages, components, graph_budget),
            ]

    return ["(no stages defined yet)"]


def _stage_list_lines(
    stages: list[StageInput], components: list[ComponentInput], max_width: int
) -> list[str]:
    """Render the stages as a table of #, name, starting materials, and products.

    Used when the component graph can't be laid out as a single DAG (still being
    built). A table — rather than arrow-joined boxes — avoids implying a stage
    order we don't actually know yet.

    Args:
        stages: Stages to list.
        components: Components, used to resolve display names.
        max_width: Columns available inside the diagram box; the table is shrunk
            to fit so it never overflows the box interior.
    """
    name_by_id = {component.id: component.display_name for component in components}
    columns = [
        Column("#", align="right", min_width=2, priority=2),
        Column("Name"),
        Column("Starting materials", priority=1),
        Column("Products", priority=0),
    ]

    def names(stage: StageInput, kind: str) -> str:
        labels = [
            name_by_id.get(link.component_id, link.component_id)
            for link in stage.stage_components
            if link.component_type == kind
        ]
        return ", ".join(labels) or "—"

    rows = [
        [str(stage.number), stage.name, names(stage, "reactant"), names(stage, "product")]
        for stage in sorted(stages, key=lambda stage: stage.number)
    ]
    return render_table(columns, rows, max_width=max_width)


def _assemble_sections(
    sections: list[tuple[str | None, list[str]]],
    dim: Callable[[str], str] = _identity,
) -> list[str]:
    """Flatten ``(title, lines)`` sections, adding greyed headers when split."""
    lines: list[str] = []
    for title, section_lines in sections:
        if title is not None:
            lines.extend([dim(title), ""])
        lines.extend(section_lines)
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines
