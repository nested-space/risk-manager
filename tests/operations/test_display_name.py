"""Tests for display-name collision/ambiguity helpers in material_operations."""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.operations import material_operations
from riskmanager_cli.operations.dmta_operations import ResolveResult
from riskmanager_cli.operations.material_operations import (
    add_material_alias,
    create_material,
    display_name_is_unambiguous,
    existing_display_names,
)
from riskmanager_cli.schema.create import MaterialAliasCreate, MaterialCreate


@pytest.mark.integration
async def test_existing_display_names_gathers_names_and_aliases(temp_env: Environment) -> None:
    """Names, display names, and aliases of all materials are returned."""
    material = await create_material(
        MaterialCreate(name="Aspirin", display_name="ASA"), env=temp_env
    )
    assert material is not None
    await add_material_alias(
        MaterialAliasCreate(material_id=UUID(str(material.id)), alias="acetylsalicylic acid"),
        env=temp_env,
    )

    names = await existing_display_names(env=temp_env)

    assert "Aspirin" in names
    assert "ASA" in names
    assert "acetylsalicylic acid" in names


@pytest.mark.integration
async def test_existing_display_names_excludes_given_id(temp_env: Environment) -> None:
    """The material identified by exclude_id is omitted from the set."""
    keep = await create_material(MaterialCreate(name="Keep"), env=temp_env)
    drop = await create_material(MaterialCreate(name="Drop"), env=temp_env)
    assert keep is not None and drop is not None

    names = await existing_display_names(exclude_id=UUID(str(drop.id)), env=temp_env)

    assert "Keep" in names
    assert "Drop" not in names


@pytest.mark.unit
async def test_display_name_is_unambiguous_returns_none_without_own_smiles() -> None:
    """No SMILES to compare against means no determination is possible."""
    assert await display_name_is_unambiguous("ASA", None) is None


@pytest.mark.unit
async def test_display_name_is_unambiguous_true_for_same_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name resolving to the material's own structure is unambiguous."""

    async def fake_augment(name: str) -> ResolveResult:
        del name
        return ResolveResult(name="x", smiles="CCO", source="pubchem")

    monkeypatch.setattr(material_operations, "augment_name", fake_augment)
    assert await display_name_is_unambiguous("ethanol", "CCO") is True


@pytest.mark.unit
async def test_display_name_is_unambiguous_false_for_different_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name resolving to a different structure is flagged ambiguous."""

    async def fake_augment(name: str) -> ResolveResult:
        del name
        return ResolveResult(name="x", smiles="c1ccccc1", source="pubchem")

    monkeypatch.setattr(material_operations, "augment_name", fake_augment)
    assert await display_name_is_unambiguous("ethanol", "CCO") is False


@pytest.mark.unit
async def test_display_name_is_unambiguous_none_when_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolved candidate yields no determination."""

    async def fake_augment(name: str) -> ResolveResult:
        del name
        return ResolveResult(name="x")

    monkeypatch.setattr(material_operations, "augment_name", fake_augment)
    assert await display_name_is_unambiguous("nonsense", "CCO") is None
