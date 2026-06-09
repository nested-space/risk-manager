"""Integration tests for riskmanager_cli.operations.manufacturing_process_operations."""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
    list_processes_for_project,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.schema.create import (
    ManufacturingProcessCreate,
    MaterialCreate,
    ProjectCreate,
)


async def _make_project(env: Environment) -> str:
    """Create a material + project and return the project UUID string."""
    material = await create_material(MaterialCreate(name="TestMaterial"), env=env)
    assert material is not None
    project = await create_project(
        ProjectCreate(
            name="TestProject",
            therapy_area=TA.ONCOLOGY,
            material_id=UUID(str(material.id)),
        ),
        env=env,
    )
    assert project is not None
    return str(project.id)


@pytest.mark.integration
async def test_create_manufacturing_process_returns_record_with_id(temp_env: Environment) -> None:
    """A manufacturing process created successfully has a non-null UUID id."""
    project_id = await _make_project(temp_env)
    result = await create_manufacturing_process(
        ManufacturingProcessCreate(project_id=UUID(project_id), route_number=1, process_number=1),
        env=temp_env,
    )
    assert result is not None
    assert result.id is not None
    assert (result.route_number, result.process_number) == (1, 1)


@pytest.mark.integration
async def test_create_duplicate_route_process_returns_none(temp_env: Environment) -> None:
    """A duplicate (route, process) tuple violates the unique constraint."""
    project_id = await _make_project(temp_env)
    first = await create_manufacturing_process(
        ManufacturingProcessCreate(project_id=UUID(project_id), route_number=1, process_number=1),
        env=temp_env,
    )
    assert first is not None
    duplicate = await create_manufacturing_process(
        ManufacturingProcessCreate(project_id=UUID(project_id), route_number=1, process_number=1),
        env=temp_env,
    )
    assert duplicate is None


@pytest.mark.integration
async def test_list_processes_for_project_returns_created(temp_env: Environment) -> None:
    """list_processes_for_project returns every process created for the project."""
    project_id = await _make_project(temp_env)
    await create_manufacturing_process(
        ManufacturingProcessCreate(project_id=UUID(project_id), route_number=1, process_number=1),
        env=temp_env,
    )
    await create_manufacturing_process(
        ManufacturingProcessCreate(project_id=UUID(project_id), route_number=1, process_number=2),
        env=temp_env,
    )
    processes = await list_processes_for_project(UUID(project_id), env=temp_env)
    labels = {(p.route_number, p.process_number) for p in processes}
    assert labels == {(1, 1), (1, 2)}
