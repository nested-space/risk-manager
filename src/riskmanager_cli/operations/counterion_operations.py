"""
Counterion CRUD and search operations.

All functions are ``async def`` and open their own database sessions via
:func:`~..database.db_session.get_db_session`. On error, they log via
``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Counterion, CounterionAlias
from ..schema.create import CounterionAliasCreate, CounterionCreate
from ..schema.update import CounterionUpdate
from ..utils.console_formatting import print_error, print_success
from .smiles_operations import canonicalize_smiles, is_valid_smiles


async def create_counterion(
    data: CounterionCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Counterion | None:
    """Create a new counterion record.

    Validates and canonicalizes the SMILES if provided.

    Args:
        data: Validated :class:`~..schema.create.CounterionCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.Counterion`; ``None`` on error.
    """
    try:
        smiles: str | None = None
        if data.smiles:
            if not is_valid_smiles(data.smiles):
                print_error(f"Invalid SMILES for counterion '{data.name}': {data.smiles}")
                return None
            smiles = canonicalize_smiles(data.smiles) or data.smiles

        async with get_db_session(env, verbose) as session:
            counterion = Counterion(
                name=data.name,
                display_name=data.display_name or data.name,
                interpret_chemically=data.interpret_chemically,
                smiles=smiles,
            )
            session.add(counterion)
            await session.commit()
            await session.refresh(counterion)
            print_success(f"Created counterion '{counterion.name}'.")
            return counterion
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create counterion: {exc}")
        return None


async def get_counterion_by_id(
    counterion_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Counterion | None:
    """Retrieve a counterion by UUID.

    Args:
        counterion_id: UUID of the counterion.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Counterion`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Counterion.get_where(session, Counterion.id == str(counterion_id))
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get counterion by ID: {exc}")
        return None


async def get_counterion_by_name(
    name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Counterion | None:
    """Retrieve a counterion by exact name.

    Args:
        name: Exact counterion name.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Counterion`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Counterion.get_where(session, Counterion.name == name)
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get counterion by name: {exc}")
        return None


async def list_counterions(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Counterion]:
    """Return all counterions ordered by name.

    Args:
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.Counterion` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Counterion.get_all(session)
            return sorted(results, key=lambda c: c.name)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list counterions: {exc}")
        return []


async def update_counterion(
    counterion_id: UUID,
    data: CounterionUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Counterion | None:
    """Update fields on an existing counterion.

    Args:
        counterion_id: UUID of the counterion to update.
        data: Validated :class:`~..schema.update.CounterionUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.Counterion`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Counterion.get_where(session, Counterion.id == str(counterion_id))
            if not results:
                print_error(f"Counterion '{counterion_id}' not found.")
                return None
            counterion = results[0]
            updates = data.model_dump(exclude_none=True)
            if "smiles" in updates and updates["smiles"]:
                canonical = canonicalize_smiles(updates["smiles"])
                updates["smiles"] = canonical or updates["smiles"]
            await counterion.update_fields(session, **updates)
            return counterion
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update counterion: {exc}")
        return None


async def delete_counterion(
    counterion_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a counterion by UUID.

    Args:
        counterion_id: UUID of the counterion to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Counterion.get_where(session, Counterion.id == str(counterion_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete counterion: {exc}")
        return False


async def add_counterion_alias(
    data: CounterionAliasCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> CounterionAlias | None:
    """Add an alias to an existing counterion.

    Args:
        data: Validated :class:`~..schema.create.CounterionAliasCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.CounterionAlias`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            alias = CounterionAlias(counterion_id=str(data.counterion_id), alias=data.alias)
            session.add(alias)
            await session.commit()
            await session.refresh(alias)
            return alias
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to add counterion alias: {exc}")
        return None
