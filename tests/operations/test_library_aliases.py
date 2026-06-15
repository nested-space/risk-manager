"""Integration tests for the library alias-count operations."""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.operations.counterion_operations import (
    add_counterion_alias,
    counterion_alias_counts,
    create_counterion,
    list_counterion_aliases,
)
from riskmanager_cli.operations.material_operations import (
    add_material_alias,
    create_material,
    list_material_aliases,
    material_alias_counts,
)
from riskmanager_cli.operations.ncrm_library_operations import (
    add_ncrm_alias,
    create_ncrm_library_entry,
    list_ncrm_aliases,
    ncrm_alias_counts,
)
from riskmanager_cli.schema.create import (
    CounterionAliasCreate,
    CounterionCreate,
    MaterialAliasCreate,
    MaterialCreate,
    NcrmLibraryAliasCreate,
    NcrmLibraryCreate,
)


@pytest.mark.integration
async def test_material_alias_counts_maps_id_to_count(temp_env: Environment) -> None:
    """material_alias_counts returns each material's alias count, omitting zeros."""
    with_aliases = await create_material(MaterialCreate(name="Aspirin"), env=temp_env)
    without = await create_material(MaterialCreate(name="Paracetamol"), env=temp_env)
    assert with_aliases is not None and without is not None
    for alias in ("ASA", "acetylsalicylic acid"):
        await add_material_alias(
            MaterialAliasCreate(material_id=UUID(str(with_aliases.id)), alias=alias), env=temp_env
        )

    counts = await material_alias_counts(temp_env)

    assert counts[str(with_aliases.id)] == 2
    assert str(without.id) not in counts


@pytest.mark.integration
async def test_ncrm_alias_counts_maps_id_to_count(temp_env: Environment) -> None:
    """ncrm_alias_counts counts aliases per NCRM library entry."""
    entry = await create_ncrm_library_entry(
        NcrmLibraryCreate(name="acetic acid", display_name="AcOH"), env=temp_env
    )
    assert entry is not None
    await add_ncrm_alias(
        NcrmLibraryAliasCreate(ncrm_library_id=UUID(str(entry.id)), alias="ethanoic acid"),
        env=temp_env,
    )

    counts = await ncrm_alias_counts(temp_env)

    assert counts[str(entry.id)] == 1


@pytest.mark.integration
async def test_counterion_alias_counts_maps_id_to_count(temp_env: Environment) -> None:
    """counterion_alias_counts counts aliases per counterion."""
    ion = await create_counterion(
        CounterionCreate(name="sulfate", display_name="H2SO4", interpret_chemically=True),
        env=temp_env,
    )
    assert ion is not None
    for alias in ("Sulphate", "Sulfate(2-)"):
        await add_counterion_alias(
            CounterionAliasCreate(counterion_id=UUID(str(ion.id)), alias=alias), env=temp_env
        )

    counts = await counterion_alias_counts(temp_env)

    assert counts[str(ion.id)] == 2


@pytest.mark.integration
async def test_alias_counts_empty_when_no_aliases(temp_env: Environment) -> None:
    """A material with no aliases yields an empty count map."""
    material = await create_material(MaterialCreate(name="Lonely"), env=temp_env)
    assert material is not None
    assert await material_alias_counts(temp_env) == {}


@pytest.mark.integration
async def test_list_material_aliases_returns_sorted_for_one_entry(temp_env: Environment) -> None:
    """list_material_aliases returns just that material's aliases, case-insensitively."""
    target = await create_material(MaterialCreate(name="Aspirin"), env=temp_env)
    other = await create_material(MaterialCreate(name="Paracetamol"), env=temp_env)
    assert target is not None and other is not None
    for alias in ("acetylsalicylic acid", "ASA"):
        await add_material_alias(
            MaterialAliasCreate(material_id=UUID(str(target.id)), alias=alias), env=temp_env
        )
    await add_material_alias(
        MaterialAliasCreate(material_id=UUID(str(other.id)), alias="APAP"), env=temp_env
    )

    aliases = await list_material_aliases(UUID(str(target.id)), temp_env)

    assert aliases == ["acetylsalicylic acid", "ASA"]


@pytest.mark.integration
async def test_list_ncrm_aliases_returns_entry_aliases(temp_env: Environment) -> None:
    """list_ncrm_aliases returns the aliases of a single NCRM entry."""
    entry = await create_ncrm_library_entry(
        NcrmLibraryCreate(name="acetic acid", display_name="AcOH"), env=temp_env
    )
    assert entry is not None
    await add_ncrm_alias(
        NcrmLibraryAliasCreate(ncrm_library_id=UUID(str(entry.id)), alias="ethanoic acid"),
        env=temp_env,
    )

    assert await list_ncrm_aliases(UUID(str(entry.id)), temp_env) == ["ethanoic acid"]


@pytest.mark.integration
async def test_list_counterion_aliases_empty_when_none(temp_env: Environment) -> None:
    """A counterion with no aliases lists as an empty list."""
    ion = await create_counterion(CounterionCreate(name="chloride"), env=temp_env)
    assert ion is not None

    assert await list_counterion_aliases(UUID(str(ion.id)), temp_env) == []
