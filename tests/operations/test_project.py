"""Integration tests for riskmanager_cli.operations.project_operations."""

from uuid import UUID, uuid4

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import (
    create_project,
    delete_project,
    get_project_by_id,
    list_projects,
    search_projects,
)
from riskmanager_cli.schema.create import MaterialCreate, ProjectCreate


async def _make_material(env: Environment, name: str = "TestMaterial") -> str:
    """Create a material and return its UUID string."""
    mat = await create_material(MaterialCreate(name=name), env=env)
    assert mat is not None
    return str(mat.id)


@pytest.mark.integration
async def test_create_project_returns_project_with_id(temp_env: Environment) -> None:
    """A project created successfully has a non-null UUID id."""
    mat_id = await _make_material(temp_env)
    result = await create_project(
        ProjectCreate(name="AlphaProject", therapy_area=TA.ONCOLOGY, material_id=UUID(mat_id)),
        env=temp_env,
    )
    assert result is not None
    assert result.id is not None
    assert result.name == "AlphaProject"


@pytest.mark.integration
async def test_get_project_by_id_returns_project(temp_env: Environment) -> None:
    """get_project_by_id retrieves the project by UUID."""
    mat_id = await _make_material(temp_env)
    created = await create_project(
        ProjectCreate(name="BetaProject", therapy_area=TA.CVRM, material_id=UUID(mat_id)),
        env=temp_env,
    )
    assert created is not None
    fetched = await get_project_by_id(UUID(str(created.id)), env=temp_env)
    assert fetched is not None
    assert fetched.name == "BetaProject"


@pytest.mark.integration
async def test_get_project_by_id_with_unknown_uuid_returns_none(temp_env: Environment) -> None:
    """get_project_by_id returns None for a UUID that does not exist."""
    result = await get_project_by_id(uuid4(), env=temp_env)
    assert result is None


@pytest.mark.integration
async def test_list_projects_returns_all_created(temp_env: Environment) -> None:
    """list_projects returns every project that has been created."""
    mat_id = await _make_material(temp_env)
    await create_project(
        ProjectCreate(name="ProjectX", therapy_area=TA.ONCOLOGY, material_id=UUID(mat_id)),
        env=temp_env,
    )
    await create_project(
        ProjectCreate(name="ProjectY", therapy_area=TA.ONCOLOGY, material_id=UUID(mat_id)),
        env=temp_env,
    )
    projects = await list_projects(env=temp_env)
    names = [p.name for p in projects]
    assert "ProjectX" in names
    assert "ProjectY" in names


@pytest.mark.integration
async def test_search_projects_returns_partial_name_matches(temp_env: Environment) -> None:
    """search_projects returns projects whose names contain the query string."""
    mat_id = await _make_material(temp_env)
    await create_project(
        ProjectCreate(name="Oncology Study", therapy_area=TA.ONCOLOGY, material_id=UUID(mat_id)),
        env=temp_env,
    )
    await create_project(
        ProjectCreate(name="Cardiology Study", therapy_area=TA.CVRM, material_id=UUID(mat_id)),
        env=temp_env,
    )
    results = await search_projects("onco", env=temp_env)
    assert len(results) == 1
    assert results[0].name == "Oncology Study"


@pytest.mark.integration
async def test_delete_project_removes_record(temp_env: Environment) -> None:
    """delete_project removes the project so it can no longer be fetched."""
    mat_id = await _make_material(temp_env)
    created = await create_project(
        ProjectCreate(name="ToDelete", therapy_area=TA.ONCOLOGY, material_id=UUID(mat_id)),
        env=temp_env,
    )
    assert created is not None
    deleted = await delete_project(UUID(str(created.id)), env=temp_env)
    assert deleted is True
    fetched = await get_project_by_id(UUID(str(created.id)), env=temp_env)
    assert fetched is None
