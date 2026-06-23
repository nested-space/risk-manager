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
from riskmanager_cli.operations.component_operations import create_component
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.manufacturing_process_risk_operations import (
    create_manufacturing_process_risk,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.operations.stage_component_operations import create_stage_component
from riskmanager_cli.operations.stage_operations import create_stage
from riskmanager_cli.operations.stage_risk_operations import create_stage_risk
from riskmanager_cli.repl.renderers.route_renderer import render_route_screen
from riskmanager_cli.schema.create import (
    ComponentCreate,
    ManufacturingProcessCreate,
    ManufacturingProcessRiskCreate,
    MaterialCreate,
    ProjectCreate,
    StageComponentCreate,
    StageCreate,
    StageRiskCreate,
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
    # No stages yet → the framed diagram shows the empty-stage placeholder.
    assert any("(no stages defined yet)" in line for line in lines)


@pytest.mark.integration
async def test_render_route_screen_shows_stage_table_when_graph_incomplete(
    temp_env: Environment,
) -> None:
    """An in-progress process falls back to a #/Name/materials/products table."""
    process = await _seed_process(temp_env)
    process_id = UUID(str(process.id))

    toluene = await create_material(
        MaterialCreate(name="Toluene", smiles="Cc1ccccc1"), env=temp_env
    )
    assert toluene is not None
    component = await create_component(
        ComponentCreate(process_id=process_id, material_id=UUID(str(toluene.id))),
        env=temp_env,
    )
    assert component is not None
    # A stage with a reactant but no product cannot form a valid DAG, forcing the
    # renderer onto the stage-list fallback.
    stage = await create_stage(
        StageCreate(process_id=process_id, name="Reaction", number=1), env=temp_env
    )
    assert stage is not None
    link = await create_stage_component(
        StageComponentCreate(
            stage_id=UUID(str(stage.id)),
            component_id=UUID(str(component.id)),
            component_type="reactant",
        ),
        env=temp_env,
    )
    assert link is not None

    lines = await render_route_screen(process, temp_env, width=100)

    assert any("showing stage list" in line for line in lines)
    header = next(line for line in lines if "Starting materials" in line)
    assert "#" in header and "Name" in header and "Products" in header
    # The reactant material appears; with no product the Products cell is "—".
    assert any("Reaction" in line and "Toluene" in line and "—" in line for line in lines)


@pytest.mark.integration
async def test_render_route_screen_renders_aggregated_risk_table(
    temp_env: Environment,
) -> None:
    """Stage and process risks render as a table under the Risks rule."""
    process = await _seed_process(temp_env)
    process_id = UUID(str(process.id))
    stage = await create_stage(
        StageCreate(process_id=process_id, name="Reaction", number=1), env=temp_env
    )
    assert stage is not None
    await create_stage_risk(
        StageRiskCreate(
            stage_id=UUID(str(stage.id)), risk_type="Safety", name="Exotherm", current_level=3
        ),
        env=temp_env,
    )
    await create_manufacturing_process_risk(
        ManufacturingProcessRiskCreate(
            manufacturing_process_id=process_id,
            risk_type="Supply",
            name="Single source",
            current_level=5,
        ),
        env=temp_env,
    )

    lines = await render_route_screen(process, temp_env, width=120)

    header = next(line for line in lines if "Component/Stage" in line)
    for column in ("Entity name", "Type", "Level", "Title", "Mitigation", "Mitigated level"):
        assert column in header
    assert any("Stage" in line and "Reaction" in line and "Exotherm" in line for line in lines)
    assert any("Process" in line and "Single source" in line for line in lines)
    assert not any("(no risks recorded)" in line for line in lines)


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
