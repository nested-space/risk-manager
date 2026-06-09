"""Integration tests for governance_cli.operations.component_operations."""

from uuid import UUID

import pytest

from governance_cli.config.settings import Environment
from governance_cli.model.enums import TA
from governance_cli.operations.component_operations import (
    create_component,
    get_component_by_id,
    list_components_for_process,
)
from governance_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from governance_cli.operations.material_operations import create_material
from governance_cli.operations.project_operations import create_project
from governance_cli.schema.create import (
    ComponentCreate,
    ManufacturingProcessCreate,
    MaterialCreate,
    ProjectCreate,
)


async def _setup_process(env: Environment) -> tuple[str, str, str]:
    """Create material → project → process and return (material_id, project_id, process_id)."""
    mat = await create_material(MaterialCreate(name="TestCompMaterial"), env=env)
    assert mat is not None
    proj = await create_project(
        ProjectCreate(
            name="CompTestProject", therapy_area=TA.ONCOLOGY, material_id=UUID(str(mat.id))
        ),
        env=env,
    )
    assert proj is not None
    process = await create_manufacturing_process(
        ManufacturingProcessCreate(project_id=UUID(str(proj.id)), route_number=1, process_number=1),
        env=env,
    )
    assert process is not None
    return str(mat.id), str(proj.id), str(process.id)


@pytest.mark.integration
async def test_create_component_returns_component(temp_env: Environment) -> None:
    """A component created successfully has a non-null UUID id."""
    mat_id, _proj_id, proc_id = await _setup_process(temp_env)
    result = await create_component(
        ComponentCreate(process_id=UUID(proc_id), material_id=UUID(mat_id)),
        env=temp_env,
    )
    assert result is not None
    assert result.id is not None
    assert str(result.process_id) == proc_id


@pytest.mark.integration
async def test_create_component_stores_control_strategy_role(temp_env: Environment) -> None:
    """control_strategy_role is persisted when provided."""
    mat_id, _proj_id, proc_id = await _setup_process(temp_env)
    result = await create_component(
        ComponentCreate(
            process_id=UUID(proc_id),
            material_id=UUID(mat_id),
            control_strategy_role="starting material",
        ),
        env=temp_env,
    )
    assert result is not None
    assert result.control_strategy_role == "starting material"


@pytest.mark.integration
async def test_get_component_by_id_returns_component(temp_env: Environment) -> None:
    """get_component_by_id retrieves the component by UUID."""
    mat_id, _proj_id, proc_id = await _setup_process(temp_env)
    created = await create_component(
        ComponentCreate(process_id=UUID(proc_id), material_id=UUID(mat_id)),
        env=temp_env,
    )
    assert created is not None
    fetched = await get_component_by_id(UUID(str(created.id)), env=temp_env)
    assert fetched is not None
    assert str(fetched.id) == str(created.id)


@pytest.mark.integration
async def test_list_components_for_process_returns_items(temp_env: Environment) -> None:
    """list_components_for_process returns all components linked to the process."""
    mat_id, _proj_id, proc_id = await _setup_process(temp_env)
    await create_component(
        ComponentCreate(process_id=UUID(proc_id), material_id=UUID(mat_id)),
        env=temp_env,
    )
    components = await list_components_for_process(UUID(proc_id), env=temp_env)
    assert len(components) == 1
    assert str(components[0].process_id) == proc_id
