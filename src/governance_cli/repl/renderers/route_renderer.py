"""Route-screen rendering helpers."""

from __future__ import annotations

from uuid import UUID

from ...config.settings import Environment
from ...model.tables import ManufacturingProcess
from ...operations.manufacturing_process_risk_operations import list_risks_for_process
from ...operations.visualization_operations import get_route_layout, get_route_risk_summary
from ...utils.manufacturing_layout_engine import RiskDict, render_risk_summary


async def render_route_screen(
    process: ManufacturingProcess,
    env: Environment,
) -> list[str]:
    """Return display lines for Route View.

    Args:
        process: Manufacturing process to render.
        env: Active database environment.

    Returns:
        Renderable output lines.
    """
    route_label = f"{process.route_number}.{process.process_number}"
    layout = await get_route_layout(UUID(str(process.id)), env)
    stage_risks = await get_route_risk_summary(UUID(str(process.id)), env)
    process_risks = await list_risks_for_process(UUID(str(process.id)), env)
    dashboard_input: list[RiskDict] = []
    for stage_risk in stage_risks:
        dashboard_input.append(dict(stage_risk))
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
    return [
        f"Route {route_label}",
        "",
        *layout.lines,
        "",
        *render_risk_summary(dashboard_input),
    ]
