"""Unit and integration tests for riskmanager_cli.operations.material_operations."""

from uuid import uuid4

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.operations.material_operations import (
    create_material,
    delete_material,
    get_material_by_id,
    list_materials,
    update_material,
)
from riskmanager_cli.schema.create import MaterialCreate
from riskmanager_cli.schema.update import MaterialUpdate


@pytest.mark.unit
async def test_create_material_with_invalid_smiles_returns_none() -> None:
    """Creating a material with an invalid SMILES string returns None without DB access."""
    result = await create_material(MaterialCreate(name="BadMaterial", smiles="NOT_VALID_SMILES!!!"))
    assert result is None


@pytest.mark.integration
async def test_create_material_returns_material_with_id(temp_env: Environment) -> None:
    """A material created successfully has a non-null UUID id."""
    result = await create_material(MaterialCreate(name="Aspirin"), env=temp_env)
    assert result is not None
    assert result.id is not None
    assert result.name == "Aspirin"


@pytest.mark.integration
async def test_create_material_display_name_defaults_to_name(temp_env: Environment) -> None:
    """Omitting display_name falls back to the material name."""
    result = await create_material(MaterialCreate(name="Aspirin"), env=temp_env)
    assert result is not None
    assert result.display_name == "Aspirin"
    assert result.interpret_chemically is False


@pytest.mark.integration
async def test_create_material_keeps_explicit_display_name_and_flag(
    temp_env: Environment,
) -> None:
    """An explicit display_name and interpret_chemically flag are persisted."""
    result = await create_material(
        MaterialCreate(name="Aspirin", display_name="ASA", interpret_chemically=True),
        env=temp_env,
    )
    assert result is not None
    assert result.display_name == "ASA"
    assert result.interpret_chemically is True


@pytest.mark.integration
async def test_create_materials_allow_duplicate_display_name(temp_env: Environment) -> None:
    """display_name is not unique: two materials may share one."""
    first = await create_material(
        MaterialCreate(name="Ethyl ester", display_name="Ester"), env=temp_env
    )
    second = await create_material(
        MaterialCreate(name="Methyl ester", display_name="Ester"), env=temp_env
    )
    assert first is not None
    assert second is not None
    assert first.display_name == second.display_name == "Ester"


@pytest.mark.integration
async def test_create_material_with_valid_smiles_stores_canonical(temp_env: Environment) -> None:
    """Valid SMILES is canonicalised and stored on the material."""
    result = await create_material(
        MaterialCreate(name="Ethanol", smiles="CCO"),
        env=temp_env,
    )
    assert result is not None
    assert result.smiles is not None


@pytest.mark.integration
async def test_create_material_with_duplicate_name_returns_none(temp_env: Environment) -> None:
    """Creating a second material with the same name returns None (unique constraint)."""
    await create_material(MaterialCreate(name="Aspirin"), env=temp_env)
    duplicate = await create_material(MaterialCreate(name="Aspirin"), env=temp_env)
    assert duplicate is None


@pytest.mark.integration
async def test_get_material_by_id_returns_material(temp_env: Environment) -> None:
    """get_material_by_id returns the correct material by UUID."""
    created = await create_material(MaterialCreate(name="Ibuprofen"), env=temp_env)
    assert created is not None
    from uuid import UUID

    fetched = await get_material_by_id(UUID(str(created.id)), env=temp_env)
    assert fetched is not None
    assert fetched.name == "Ibuprofen"


@pytest.mark.integration
async def test_get_material_by_id_with_unknown_uuid_returns_none(temp_env: Environment) -> None:
    """get_material_by_id returns None when the UUID does not exist."""
    from uuid import UUID

    result = await get_material_by_id(UUID(str(uuid4())), env=temp_env)
    assert result is None


@pytest.mark.integration
async def test_list_materials_returns_all_created(temp_env: Environment) -> None:
    """list_materials returns every material that has been created."""
    await create_material(MaterialCreate(name="MaterialA"), env=temp_env)
    await create_material(MaterialCreate(name="MaterialB"), env=temp_env)
    materials = await list_materials(env=temp_env)
    names = [m.name for m in materials]
    assert "MaterialA" in names
    assert "MaterialB" in names


@pytest.mark.integration
async def test_update_material_persists_new_fields(temp_env: Environment) -> None:
    """update_material applies the payload and returns the updated material."""
    from uuid import UUID

    created = await create_material(MaterialCreate(name="Paracetamol"), env=temp_env)
    assert created is not None
    updated = await update_material(
        UUID(str(created.id)),
        MaterialUpdate(display_name="APAP", interpret_chemically=True),
        env=temp_env,
    )
    assert updated is not None
    assert updated.display_name == "APAP"
    assert updated.interpret_chemically is True
    fetched = await get_material_by_id(UUID(str(created.id)), env=temp_env)
    assert fetched is not None
    assert fetched.display_name == "APAP"


@pytest.mark.integration
async def test_update_material_with_unknown_uuid_returns_none(temp_env: Environment) -> None:
    """update_material returns None when the material does not exist."""
    result = await update_material(uuid4(), MaterialUpdate(display_name="X"), env=temp_env)
    assert result is None


@pytest.mark.integration
async def test_delete_material_removes_record(temp_env: Environment) -> None:
    """delete_material removes the material so it can no longer be fetched."""
    from uuid import UUID

    created = await create_material(MaterialCreate(name="ToDelete"), env=temp_env)
    assert created is not None
    deleted = await delete_material(UUID(str(created.id)), env=temp_env)
    assert deleted is True
    fetched = await get_material_by_id(UUID(str(created.id)), env=temp_env)
    assert fetched is None
