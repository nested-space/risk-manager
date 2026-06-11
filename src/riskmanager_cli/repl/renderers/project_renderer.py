"""Project-screen rendering helpers."""

from __future__ import annotations

from uuid import UUID

from ...config.settings import Environment
from ...model.tables import Project
from ...operations.manufacturing_process_operations import list_processes_for_project
from ...operations.manufacturing_process_risk_operations import list_risks_for_process
from ...operations.material_operations import get_material_by_id


async def render_project_screen(
    project: Project,
    env: Environment,
    route_lines: list[str] | None = None,
) -> list[str]:
    """Return display lines for the Project Screen.

    Args:
        project: Project to render.
        env: Active database environment.
        route_lines: Pre-rendered lines for the navigable routes pick-list. When
            ``None`` (e.g. a non-interactive render) a plain route count is shown.

    Returns:
        Renderable output lines.
    """
    material = await get_material_by_id(UUID(str(project.material_id)), env)
    processes = await list_processes_for_project(UUID(str(project.id)), env)
    summary = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for process in processes:
        risks = await list_risks_for_process(UUID(str(process.id)), env)
        for risk in risks:
            level = risk.current_level or 0
            if level >= 9:
                summary["Critical"] += 1
            elif level >= 7:
                summary["High"] += 1
            elif level >= 5:
                summary["Medium"] += 1
            else:
                summary["Low"] += 1

    routes_block = route_lines if route_lines is not None else [f"{len(processes)} total"]
    return [
        project.name,
        "",
        f"Therapy area: {project.therapy_area.value}",
        f"Material SMILES: {material.smiles if material and material.smiles else '-'}",
        "Routes / processes:",
        "",
        *routes_block,
        "",
        "Risk summary",
        "  Critical  High  Medium  Low",
        (
            f"  {summary['Critical']:^8}  {summary['High']:^4}  "
            f"{summary['Medium']:^6}  {summary['Low']:^3}"
        ),
    ]
