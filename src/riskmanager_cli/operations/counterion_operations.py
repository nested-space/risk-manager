"""
Counterion CRUD and search operations.

All functions are ``async def`` and open their own database sessions via
:func:`~..database.db_session.get_db_session`. On error, they log via
``print_error`` and return ``None`` / ``[]`` / ``False``. The common CRUD
shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`; only
counterion-specific logic (SMILES validation, alias aggregation) lives here.
"""

from collections import Counter
from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Counterion, CounterionAlias
from ..schema.create import CounterionAliasCreate, CounterionCreate
from ..schema.update import CounterionUpdate
from ..utils.console_formatting import print_error
from .base_operations import (
    db_operation,
    generic_create,
    generic_delete_by_id,
    generic_get_by_id,
    generic_list,
    generic_update,
)
from .smiles_operations import canonicalize_smiles, is_valid_smiles


@db_operation(default=None, error="Failed to create counterion")
async def create_counterion(
    data: CounterionCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Counterion | None:
    """Create a new counterion record, validating/canonicalizing any SMILES.

    Args:
        data: Validated :class:`~..schema.create.CounterionCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.Counterion`; ``None`` on error.
    """
    smiles: str | None = None
    if data.smiles:
        if not is_valid_smiles(data.smiles):
            print_error(f"Invalid SMILES for counterion '{data.name}': {data.smiles}")
            return None
        smiles = canonicalize_smiles(data.smiles) or data.smiles

    counterion = Counterion(
        name=data.name,
        display_name=data.display_name or data.name,
        interpret_chemically=data.interpret_chemically,
        smiles=smiles,
    )
    return await generic_create(
        counterion, "counterion", env, verbose, success_message=f"Created counterion '{data.name}'."
    )


async def get_counterion_by_id(
    counterion_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Counterion | None:
    """Retrieve a counterion by UUID; ``None`` if not found."""
    return await generic_get_by_id(Counterion, counterion_id, "counterion", env, verbose)


@db_operation(default=None, error="Failed to get counterion by name")
async def get_counterion_by_name(
    name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Counterion | None:
    """Retrieve a counterion by exact name; ``None`` if not found."""
    async with get_db_session(env, verbose) as session:
        results = await Counterion.get_where(session, Counterion.name == name)
        return results[0] if results else None


async def list_counterions(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Counterion]:
    """Return all counterions ordered by name."""
    return await generic_list(Counterion, "counterions", env, verbose, sort_key=lambda c: c.name)


@db_operation(default={}, error="Failed to count counterion aliases")
async def counterion_alias_counts(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> dict[str, int]:
    """Return a mapping of counterion id to its alias count.

    Counterions with no aliases are absent from the mapping.
    """
    async with get_db_session(env, verbose) as session:
        aliases = await CounterionAlias.get_all(session)
        return dict(Counter(str(alias.counterion_id) for alias in aliases))


@db_operation(default=[], error="Failed to list counterion aliases")
async def list_counterion_aliases(
    counterion_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[str]:
    """Return the aliases of a single counterion, sorted case-insensitively."""
    async with get_db_session(env, verbose) as session:
        aliases = await CounterionAlias.get_where(
            session, CounterionAlias.counterion_id == str(counterion_id)
        )
        return sorted((alias.alias for alias in aliases), key=str.casefold)


async def update_counterion(
    counterion_id: UUID,
    data: CounterionUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Counterion | None:
    """Update fields on an existing counterion; ``None`` on not-found or error."""
    updates = data.model_dump(exclude_none=True)
    if updates.get("smiles"):
        updates["smiles"] = canonicalize_smiles(updates["smiles"]) or updates["smiles"]
    return await generic_update(
        Counterion, counterion_id, "counterion", updates, env=env, verbose=verbose
    )


async def delete_counterion(
    counterion_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a counterion by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(Counterion, counterion_id, "counterion", env, verbose)


async def add_counterion_alias(
    data: CounterionAliasCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> CounterionAlias | None:
    """Add an alias to an existing counterion; ``None`` on error."""
    alias = CounterionAlias(counterion_id=str(data.counterion_id), alias=data.alias)
    return await generic_create(alias, "counterion alias", env, verbose)
