"""Tests for first-run reference-library seeding (``operations/seed_operations``)."""

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.database.db_session import get_db_session
from riskmanager_cli.model.tables import Counterion, CounterionAlias, NcrmLibrary
from riskmanager_cli.operations.seed_operations import (
    COUNTERION_SEED_FILE,
    NCRM_SEED_FILE,
    SeedEntry,
    load_seed_entries,
    seed_counterions,
    seed_ncrm,
)


@pytest.mark.unit
def test_load_seed_entries_counterions_well_formed() -> None:
    entries = load_seed_entries(COUNTERION_SEED_FILE)
    assert len(entries) == 24
    first = entries[0]
    assert set(first) == {"name", "display_name", "interpret_chemically", "smiles", "aliases"}
    assert all(entry["name"] for entry in entries)
    assert isinstance(first["aliases"], list)


@pytest.mark.unit
def test_load_seed_entries_ncrm_count() -> None:
    entries = load_seed_entries(NCRM_SEED_FILE)
    assert len(entries) == 325
    assert all(entry["name"] for entry in entries)


@pytest.mark.integration
async def test_seed_counterions_creates_rows_and_aliases(temp_env: Environment) -> None:
    entries = load_seed_entries(COUNTERION_SEED_FILE)
    expected_aliases = sum(len(entry["aliases"]) for entry in entries)

    counts = await seed_counterions(entries, temp_env)

    assert counts == {"created": 24, "skipped": 0, "errors": 0}
    async with get_db_session(temp_env) as session:
        assert len(await Counterion.get_all(session)) == 24
        assert len(await CounterionAlias.get_all(session)) == expected_aliases


@pytest.mark.integration
async def test_seed_ncrm_creates_all_rows(temp_env: Environment) -> None:
    entries = load_seed_entries(NCRM_SEED_FILE)

    counts = await seed_ncrm(entries, temp_env)

    assert counts == {"created": 325, "skipped": 0, "errors": 0}
    async with get_db_session(temp_env) as session:
        assert len(await NcrmLibrary.get_all(session)) == 325


@pytest.mark.integration
async def test_seed_progress_callback_invoked_per_row(temp_env: Environment) -> None:
    entries = load_seed_entries(COUNTERION_SEED_FILE)
    seen: list[tuple[int, int]] = []

    def record(done: int, total: int) -> None:
        seen.append((done, total))

    await seed_counterions(entries, temp_env, progress=record)

    assert len(seen) == len(entries)
    assert seen[-1] == (len(entries), len(entries))


@pytest.mark.integration
async def test_seed_skips_blank_name_row(temp_env: Environment) -> None:
    entries: list[SeedEntry] = [
        {
            "name": "  ",
            "display_name": "blank",
            "interpret_chemically": False,
            "smiles": None,
            "aliases": [],
        }
    ]

    counts = await seed_counterions(entries, temp_env)

    assert counts == {"created": 0, "skipped": 1, "errors": 0}


@pytest.mark.integration
async def test_seed_duplicate_name_counted_as_error_not_fatal(temp_env: Environment) -> None:
    entries: list[SeedEntry] = [
        {
            "name": "chloride",
            "display_name": "Cl-",
            "interpret_chemically": True,
            "smiles": None,
            "aliases": ["Cl"],
        },
        {  # duplicate name violates the unique constraint
            "name": "chloride",
            "display_name": "dup",
            "interpret_chemically": True,
            "smiles": None,
            "aliases": [],
        },
        {
            "name": "bromide",
            "display_name": "Br-",
            "interpret_chemically": True,
            "smiles": None,
            "aliases": [],
        },
    ]

    counts = await seed_counterions(entries, temp_env)

    # The bad row is isolated by its SAVEPOINT; the following row still commits.
    assert counts == {"created": 2, "skipped": 0, "errors": 1}
    async with get_db_session(temp_env) as session:
        assert len(await Counterion.get_all(session)) == 2


@pytest.mark.integration
async def test_seed_invalid_smiles_counted_as_error(temp_env: Environment) -> None:
    entries: list[SeedEntry] = [
        {
            "name": "weird",
            "display_name": "weird",
            "interpret_chemically": True,
            "smiles": "not-a-valid-smiles-%%%",
            "aliases": [],
        }
    ]

    counts = await seed_counterions(entries, temp_env)

    assert counts == {"created": 0, "skipped": 0, "errors": 1}
