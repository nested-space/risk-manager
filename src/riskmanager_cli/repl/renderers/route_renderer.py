"""Route-screen rendering helpers."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from ...config.settings import Environment
from ...model.tables import ManufacturingProcess
from ...operations.manufacturing_process_risk_operations import list_risks_for_process
from ...operations.visualization_operations import (
    get_graph_inputs,
    get_route_layout,
    get_route_risk_summary,
    get_unconnected_component_names,
)
from ...utils.component_graph_layout import IncompleteProcessError, split_for_width
from ...utils.manufacturing_layout_engine import RiskDict, render_risk_summary
from .box import render_box
from .tables import section_rule, section_width

# Box chrome consumed before the graph: two reserved screen margins, two box
# borders, and ``2 * _PAD_X`` interior padding columns.
_PAD_X = 2
_PAD_Y = 2
_RESERVED = 2


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
    # ``render_risk_summary`` already indents its rows into the body gutter.
    risk_body = render_risk_summary(await _risk_dashboard(process, env), include_header=False)
    return [
        section_rule(process_title, rule_width),
        "",
        *boxed_diagram,
        *warning_lines,
        "",
        section_rule("Risks", rule_width),
        "",
        *risk_body,
    ]


async def _risk_dashboard(process: ManufacturingProcess, env: Environment) -> list[RiskDict]:
    """Collect stage and process risks into the dashboard's input rows."""
    stage_risks = await get_route_risk_summary(UUID(str(process.id)), env)
    process_risks = await list_risks_for_process(UUID(str(process.id)), env)
    dashboard_input: list[RiskDict] = [dict(stage_risk) for stage_risk in stage_risks]
    for process_risk in process_risks:
        dashboard_input.append(
            {
                "name": process_risk.name,
                "risk_type": process_risk.risk_type,
                "current_level": process_risk.current_level,
                "mitigated_level": process_risk.mitigated_level,
                "component_name": "Process",
            }
        )
    return dashboard_input


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
            pass

    layout = await get_route_layout(UUID(str(process.id)), env)
    return ["(process graph incomplete — showing stage list)", "", *layout.lines]


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
