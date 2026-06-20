"""Tests for the shared operations scaffolding in base_operations.

Covers the ``db_operation`` decorator's success/error paths and the typed
``generic_*`` CRUD helpers that the entity modules now delegate to.
"""

from uuid import UUID, uuid4

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.tables import Counterion
from riskmanager_cli.operations.base_operations import (
    db_operation,
    generic_check_exists,
    generic_create,
    generic_delete_by_id,
    generic_get_by_id,
    generic_list,
    generic_update,
)


@pytest.mark.unit
async def test_db_operation_returns_wrapped_result_on_success() -> None:
    """The decorator passes through the wrapped coroutine's result."""

    @db_operation(default=-1, error="boom")
    async def add(a: int, b: int) -> int:
        return a + b

    assert await add(2, 3) == 5


@pytest.mark.unit
async def test_db_operation_returns_default_on_exception() -> None:
    """The decorator swallows exceptions and returns the default."""

    @db_operation(default=-1, error="boom")
    async def explode() -> int:
        raise RuntimeError("kaboom")

    assert await explode() == -1


async def _make_counterion(env: Environment, name: str = "Chloride") -> Counterion:
    created = await generic_create(Counterion(name=name, display_name=name), "counterion", env=env)
    assert created is not None
    return created


@pytest.mark.integration
async def test_generic_create_persists_and_returns_instance(temp_env: Environment) -> None:
    """generic_create commits the instance and returns it refreshed."""
    created = await _make_counterion(temp_env)
    assert created.id is not None
    assert created.name == "Chloride"


@pytest.mark.integration
async def test_generic_get_by_id_roundtrip(temp_env: Environment) -> None:
    """generic_get_by_id returns the created entity and None for unknown ids."""
    created = await _make_counterion(temp_env)
    fetched = await generic_get_by_id(Counterion, UUID(str(created.id)), "counterion", temp_env)
    assert fetched is not None and fetched.name == "Chloride"
    assert await generic_get_by_id(Counterion, uuid4(), "counterion", temp_env) is None


@pytest.mark.integration
async def test_generic_check_exists(temp_env: Environment) -> None:
    """generic_check_exists reflects presence/absence of the row."""
    created = await _make_counterion(temp_env)
    assert await generic_check_exists(Counterion, UUID(str(created.id)), "counterion", temp_env)
    assert not await generic_check_exists(Counterion, uuid4(), "counterion", temp_env)


@pytest.mark.integration
async def test_generic_list_sorts_with_key(temp_env: Environment) -> None:
    """generic_list returns all rows, ordered by the supplied sort key."""
    await _make_counterion(temp_env, "Sulfate")
    await _make_counterion(temp_env, "Chloride")
    rows = await generic_list(Counterion, "counterion", temp_env, sort_key=lambda c: c.name)
    assert [c.name for c in rows] == ["Chloride", "Sulfate"]


@pytest.mark.integration
async def test_generic_update_applies_changes(temp_env: Environment) -> None:
    """generic_update writes the field updates and returns the entity."""
    created = await _make_counterion(temp_env)
    updated = await generic_update(
        Counterion, UUID(str(created.id)), "counterion", {"display_name": "Cl-"}, env=temp_env
    )
    assert updated is not None and updated.display_name == "Cl-"


@pytest.mark.integration
async def test_generic_update_unknown_id_returns_none(temp_env: Environment) -> None:
    """generic_update returns None when the entity does not exist."""
    result = await generic_update(
        Counterion, uuid4(), "counterion", {"display_name": "x"}, env=temp_env
    )
    assert result is None


@pytest.mark.integration
async def test_generic_delete_by_id(temp_env: Environment) -> None:
    """generic_delete_by_id removes the row and reports found/not-found."""
    created = await _make_counterion(temp_env)
    assert await generic_delete_by_id(Counterion, UUID(str(created.id)), "counterion", temp_env)
    assert not await generic_delete_by_id(Counterion, uuid4(), "counterion", temp_env)
