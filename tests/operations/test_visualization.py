"""Integration tests for riskmanager_cli.operations.visualization_operations.

Exercises the component-DAG bridge end-to-end against a real (in-memory) SQLite
database, including the multi-stage assignment that gives one component several
StageComponent rows.
"""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.operations.component_operations import (
    create_component,
    list_components_for_process,
)
from riskmanager_cli.operations.component_risks_operations import create_component_risk
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.manufacturing_process_risk_operations import (
    create_manufacturing_process_risk,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.operations.stage_component_operations import (
    create_stage_component,
    list_stage_components,
)
from riskmanager_cli.operations.stage_operations import create_stage, list_stages_for_process
from riskmanager_cli.operations.stage_risk_operations import create_stage_risk
from riskmanager_cli.operations.visualization_operations import (
    get_aggregated_route_risks,
    get_graph_inputs,
    get_unconnected_component_names,
)
from riskmanager_cli.schema.create import (
    ComponentCreate,
    ComponentRiskCreate,
    ManufacturingProcessCreate,
    ManufacturingProcessRiskCreate,
    MaterialCreate,
    ProjectCreate,
    StageComponentCreate,
    StageCreate,
    StageRiskCreate,
)
from riskmanager_cli.utils.component_graph_layout import render_component_graph


async def _new_component(env: Environment, process_id: str, name: str) -> str:
    material = await create_material(MaterialCreate(name=name), env=env)
    assert material is not None
    component = await create_component(
        ComponentCreate(process_id=UUID(process_id), material_id=UUID(str(material.id))),
        env=env,
    )
    assert component is not None
    return str(component.id)


async def _setup_process(env: Environment) -> str:
    seed = await create_material(MaterialCreate(name="Seed"), env=env)
    assert seed is not None
    project = await create_project(
        ProjectCreate(name="VizProject", therapy_area=TA.ONCOLOGY, material_id=UUID(str(seed.id))),
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
    return str(process.id)


async def _build_linear_process(env: Environment) -> tuple[str, str]:
    """Build A→B→C across two stages; return (process_id, component_B_id)."""
    process_id = await _setup_process(env)
    comp_a = await _new_component(env, process_id, "A")
    comp_b = await _new_component(env, process_id, "B")
    comp_c = await _new_component(env, process_id, "C")

    stage1 = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Stage 1", number=1), env=env
    )
    stage2 = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Stage 2", number=2), env=env
    )
    assert stage1 is not None and stage2 is not None

    for stage_id, component_id, role in [
        (stage1.id, comp_a, "reactant"),
        (stage1.id, comp_b, "product"),
        (stage2.id, comp_b, "reactant"),
        (stage2.id, comp_c, "product"),
    ]:
        link = await create_stage_component(
            StageComponentCreate(
                stage_id=UUID(str(stage_id)),
                component_id=UUID(component_id),
                component_type=role,
            ),
            env=env,
        )
        assert link is not None
    return process_id, comp_b


@pytest.mark.integration
async def test_component_assigned_to_two_stages_creates_two_links_one_component(
    temp_env: Environment,
) -> None:
    """The same component B is product of stage 1 and reactant of stage 2."""
    process_id, comp_b = await _build_linear_process(temp_env)

    # Find both stages and confirm B appears in each with a distinct role,
    # while remaining a single component record.
    components = await list_components_for_process(UUID(process_id), env=temp_env)
    assert len(components) == 3  # A, B, C — B was NOT duplicated

    stages = await list_stages_for_process(UUID(process_id), env=temp_env)
    roles_for_b = []
    for stage in stages:
        for link in await list_stage_components(UUID(str(stage.id)), env=temp_env):
            if str(link.component_id) == comp_b:
                roles_for_b.append(link.component_type)
    assert sorted(roles_for_b) == ["product", "reactant"]


@pytest.mark.integration
async def test_get_graph_inputs_returns_stages_and_components(
    temp_env: Environment,
) -> None:
    """A complete A→B→C process yields its stages and components, renderable to a DAG."""
    process_id, _comp_b = await _build_linear_process(temp_env)
    inputs = await get_graph_inputs(UUID(process_id), env=temp_env)
    assert inputs is not None
    stages, components = inputs
    assert len(stages) == 2
    assert {c.display_name for c in components} == {"A", "B", "C"}
    # is_isolated is carried through (defaults to True for these components).
    assert all(c.is_isolated for c in components)

    joined = "\n".join(render_component_graph(stages, components))
    for name in ("A", "B", "C"):
        assert name in joined


@pytest.mark.integration
async def test_get_graph_inputs_returns_none_when_no_stages(
    temp_env: Environment,
) -> None:
    """A process with no stages yet falls back (returns None)."""
    process_id = await _setup_process(temp_env)
    assert await get_graph_inputs(UUID(process_id), env=temp_env) is None


@pytest.mark.integration
async def test_unconnected_components_lists_only_unassigned(
    temp_env: Environment,
) -> None:
    """A component never assigned to a stage is reported; assigned ones are not."""
    process_id, _comp_b = await _build_linear_process(temp_env)
    # A, B, C are all assigned. Add an orphan component with no stage link.
    await _new_component(temp_env, process_id, "Orphan")

    unconnected = await get_unconnected_component_names(UUID(process_id), env=temp_env)
    assert unconnected == ["Orphan"]


@pytest.mark.integration
async def test_unconnected_components_empty_when_all_assigned(
    temp_env: Environment,
) -> None:
    """When every component is assigned to a stage, there are no orphans."""
    process_id, _comp_b = await _build_linear_process(temp_env)
    assert await get_unconnected_component_names(UUID(process_id), env=temp_env) == []


@pytest.mark.integration
async def test_aggregated_route_risks_collects_stage_component_and_process(
    temp_env: Environment,
) -> None:
    """Risks from a stage, a component, and the process are all aggregated."""
    process_id, comp_b = await _build_linear_process(temp_env)
    stage = (await list_stages_for_process(UUID(process_id), env=temp_env))[0]

    await create_stage_risk(
        StageRiskCreate(
            stage_id=UUID(str(stage.id)), risk_type="Safety", name="Exotherm", current_level=3
        ),
        env=temp_env,
    )
    await create_component_risk(
        ComponentRiskCreate(
            component_id=UUID(comp_b),
            risk_type="Quality",
            name="Impurity",
            current_level=2,
            proposed_mitigation="Recrystallise",
            mitigated_level=1,
        ),
        env=temp_env,
    )
    await create_manufacturing_process_risk(
        ManufacturingProcessRiskCreate(
            manufacturing_process_id=UUID(process_id),
            risk_type="Supply",
            name="Single source",
            current_level=5,
        ),
        env=temp_env,
    )

    risks = await get_aggregated_route_risks(UUID(process_id), env=temp_env)

    by_name = {risk.name: risk for risk in risks}
    assert by_name["Exotherm"].source == "Stage"
    assert by_name["Exotherm"].entity_name == stage.name
    assert by_name["Impurity"].source == "Component"
    assert by_name["Impurity"].entity_name == "B"
    assert by_name["Impurity"].proposed_mitigation == "Recrystallise"
    assert by_name["Single source"].source == "Process"
    assert by_name["Single source"].entity_name == "—"
    # Highest current_level first.
    assert [risk.name for risk in risks] == ["Single source", "Exotherm", "Impurity"]


@pytest.mark.integration
async def test_aggregated_route_risks_empty_when_none_recorded(
    temp_env: Environment,
) -> None:
    """A process with no risks anywhere yields an empty list."""
    process_id, _comp_b = await _build_linear_process(temp_env)
    assert await get_aggregated_route_risks(UUID(process_id), env=temp_env) == []
