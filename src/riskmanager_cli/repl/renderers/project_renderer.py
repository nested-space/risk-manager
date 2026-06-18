"""Project-screen rendering helpers.

Renders a project as a sectioned page in the same style as the Stage Focus
screen (see ``renderers/stage_renderer.py``): a section-title rule above an
indented body, built from the shared ``section_rule`` / ``render_table``
primitives in ``renderers/layout/table.py``. The page has three sections — ``Project
Details`` and ``Risks`` as static box tables, and ``Routes`` as the navigable
pick-list rendered by the caller.
"""

from __future__ import annotations

from uuid import UUID

from ...config.settings import Environment
from ...model.severity import SEVERITY_BY_LEVEL, severity_name
from ...model.tables import Project
from ...operations.manufacturing_process_operations import list_processes_for_project
from ...operations.manufacturing_process_risk_operations import list_risks_for_process
from ...operations.material_operations import get_material_by_id
from ...repl_engine.layout import Column, render_table, section_rule, section_width

_BODY_INDENT = "  "


def _section(title: str, body: list[str], width: int) -> list[str]:
    """Return a titled section: a rule at column zero, a blank, then *body*.

    Body lines are indented two columns so they sit under the rule's title in
    the same gutter the Stage Focus page uses; blank body lines stay empty.
    """
    indented = [f"{_BODY_INDENT}{line}" if line else "" for line in body]
    return [section_rule(title, width), "", *indented]


async def render_project_screen(
    project: Project,
    env: Environment,
    route_lines: list[str] | None = None,
    width: int = 80,
) -> list[str]:
    """Return display lines for the Project Screen.

    Args:
        project: Project to render.
        env: Active database environment.
        route_lines: Pre-rendered lines for the navigable routes pick-list. When
            ``None`` (e.g. a non-interactive render) a plain route count is shown.
        width: Terminal width; section rules use the shared standard width.

    Returns:
        Renderable output lines: ``Project Details``, ``Routes``, and ``Risks``
        sections, each a titled rule above an indented body.
    """
    material = await get_material_by_id(UUID(str(project.material_id)), env)
    processes = await list_processes_for_project(UUID(str(project.id)), env)
    summary = {name: 0 for name in SEVERITY_BY_LEVEL.values()}
    for process in processes:
        risks = await list_risks_for_process(UUID(str(process.id)), env)
        for risk in risks:
            name = severity_name(risk.current_level)
            if name in summary:
                summary[name] += 1

    # Two columns are lost to the screen inset and two to the section body indent.
    detail_table = render_table(
        [Column("Property"), Column("Value")],
        [
            ["Name", project.name],
            ["Therapy Area", project.therapy_area.value],
            ["SMILES", material.smiles if material and material.smiles else "-"],
        ],
        max_width=width - 4,
    )
    risk_table = render_table(
        [Column("Level"), Column("Number", align="right")],
        [[name, str(summary[name])] for name in SEVERITY_BY_LEVEL.values()],
        max_width=width - 4,
    )
    routes_block = route_lines if route_lines is not None else [f"{len(processes)} total"]

    rule_width = section_width(width)
    return [
        *_section("Project Details", detail_table, rule_width),
        "",
        *_section("Routes", routes_block, rule_width),
        "",
        *_section("Risks", risk_table, rule_width),
    ]
