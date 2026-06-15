"""Integration tests for riskmanager_cli.operations.component_operations."""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.operations.component_operations import (
    component_display_name,
    create_component,
    format_salt_form,
    get_component_by_id,
    list_components_for_process,
)
from riskmanager_cli.operations.component_salt_operations import create_component_salt
from riskmanager_cli.operations.counterion_operations import create_counterion
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.schema.create import (
    ComponentCreate,
    ComponentSaltCreate,
    CounterionCreate,
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


@pytest.mark.parametrize(
    ("base", "salts", "expected"),
    [
        ("A", [], "A"),
        ("A", [(2, "B")], "A·2B"),
        ("A", [(1, "B")], "A·B"),
        ("A", [(None, "B")], "A·B"),
        ("A", [(0.5, "C")], "A·0.5C"),
        ("A", [(2, "B"), (0.5, "C")], "A·2B·0.5C"),
    ],
)
def test_format_salt_form(base: str, salts: list[tuple[float | None, str]], expected: str) -> None:
    """Salt-form names chain salts and omit a stoichiometry of 1 or None."""
    assert format_salt_form(base, salts) == expected


@pytest.mark.integration
async def test_component_display_name_includes_salt(temp_env: Environment) -> None:
    """component_display_name resolves the material base plus its salts."""
    mat_id, _proj_id, proc_id = await _setup_process(temp_env)
    component = await create_component(
        ComponentCreate(process_id=UUID(proc_id), material_id=UUID(mat_id)),
        env=temp_env,
    )
    assert component is not None

    # Bare material, no salts: just the material name.
    assert await component_display_name(component, temp_env) == "TestCompMaterial"

    counterion = await create_counterion(CounterionCreate(name="B"), env=temp_env)
    assert counterion is not None
    salt = await create_component_salt(
        ComponentSaltCreate(
            component_id=UUID(str(component.id)),
            counterion_id=UUID(str(counterion.id)),
            stoichiometry=2.0,
        ),
        env=temp_env,
    )
    assert salt is not None

    assert await component_display_name(component, temp_env) == "TestCompMaterial·2B"
