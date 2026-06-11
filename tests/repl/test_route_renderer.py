"""Integration tests for the Route sectioned-page renderer.

Exercises ``render_route_screen`` against a real (in-memory) SQLite database,
seeding a project with a manufacturing process so the section rules, the framed
manufacturing-route diagram, and the risk section render from genuine operation
results.
"""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.model.tables import ManufacturingProcess
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.repl.renderers.route_renderer import render_route_screen
from riskmanager_cli.schema.create import (
    ManufacturingProcessCreate,
    MaterialCreate,
    ProjectCreate,
)


async def _seed_process(env: Environment) -> ManufacturingProcess:
    """Seed a project with one manufacturing process (route 1, process 1)."""
    material = await create_material(MaterialCreate(name="Benzene", smiles="C1=CC=CC=C1"), env=env)
    assert material is not None
    project = await create_project(
        ProjectCreate(name="Test", therapy_area=TA.ONCOLOGY, material_id=UUID(str(material.id))),
        env=env,
    )
    assert project is not None
    process = await create_manufacturing_process(
        ManufacturingProcessCreate(
            project_id=UUID(str(project.id)), route_number=1, process_number=1
        ),
        env=env,
    )
    assert process is not None
    return process


@pytest.mark.integration
async def test_render_route_screen_has_section_rules_and_framed_diagram(
    temp_env: Environment,
) -> None:
    """The page renders a process rule, a boxed diagram, and a Risks rule."""
    process = await _seed_process(temp_env)

    lines = await render_route_screen(process, temp_env, width=100)

    assert any("─ Route 1 Process 1 " in line for line in lines)
    assert any("─ Risks " in line for line in lines)
    # The diagram is framed in a unicode box.
    assert any(line.startswith("┌") and line.endswith("┐") for line in lines)
    assert any(line.startswith("└") and line.endswith("┘") for line in lines)
    # With no risks recorded the body shows the placeholder under the rule.
    risks_index = next(i for i, line in enumerate(lines) if "─ Risks " in line)
    assert any("(no risks recorded)" in line for line in lines[risks_index:])


@pytest.mark.integration
async def test_render_route_screen_box_spans_reserved_width(
    temp_env: Environment,
) -> None:
    """The framed diagram spans the terminal width minus the reserved margins."""
    process = await _seed_process(temp_env)
    width = 100

    lines = await render_route_screen(process, temp_env, width=width)

    top = next(line for line in lines if line.startswith("┌"))
    assert len(top) == width - 2  # two reserved screen-inset columns
