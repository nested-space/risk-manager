"""
NCRM library CRUD and search operations.

All functions are ``async def`` and open their own database sessions. On error,
they log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import NcrmLibrary, NcrmLibraryAlias
from ..schema.create import NcrmLibraryAliasCreate, NcrmLibraryCreate
from ..schema.update import NcrmLibraryUpdate
from ..utils.console_formatting import print_error, print_success
from .smiles_operations import canonicalize_smiles, is_valid_smiles


async def create_ncrm_library_entry(
    data: NcrmLibraryCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibrary | None:
    """Create a new NCRM library entry.

    Args:
        data: Validated :class:`~..schema.create.NcrmLibraryCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.NcrmLibrary`; ``None`` on error.
    """
    try:
        smiles: str | None = None
        if data.smiles:
            if not is_valid_smiles(data.smiles):
                print_error(f"Invalid SMILES for NCRM '{data.display_name}': {data.smiles}")
                return None
            smiles = canonicalize_smiles(data.smiles) or data.smiles

        async with get_db_session(env, verbose) as session:
            entry = NcrmLibrary(
                display_name=data.display_name,
                common_name=data.common_name,
                interpret_chemically=data.interpret_chemically,
                smiles=smiles,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            print_success(f"Created NCRM entry '{entry.display_name}'.")
            return entry
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create NCRM entry: {exc}")
        return None


async def get_ncrm_by_id(
    ncrm_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibrary | None:
    """Retrieve an NCRM library entry by UUID.

    Args:
        ncrm_id: UUID of the NCRM entry.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.NcrmLibrary`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await NcrmLibrary.get_where(session, NcrmLibrary.id == str(ncrm_id))
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get NCRM entry by ID: {exc}")
        return None


async def get_ncrm_by_display_name(
    display_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibrary | None:
    """Retrieve an NCRM library entry by its display name.

    Args:
        display_name: Exact display name string.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.NcrmLibrary`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await NcrmLibrary.get_where(session, NcrmLibrary.display_name == display_name)
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get NCRM entry by display name: {exc}")
        return None


async def list_ncrm_library(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[NcrmLibrary]:
    """Return all NCRM library entries ordered by display name.

    Args:
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.NcrmLibrary` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await NcrmLibrary.get_all(session)
            return sorted(results, key=lambda n: n.display_name)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list NCRM library: {exc}")
        return []


async def update_ncrm_library_entry(
    ncrm_id: UUID,
    data: NcrmLibraryUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibrary | None:
    """Update fields on an existing NCRM library entry.

    Args:
        ncrm_id: UUID of the NCRM entry to update.
        data: Validated :class:`~..schema.update.NcrmLibraryUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.NcrmLibrary`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await NcrmLibrary.get_where(session, NcrmLibrary.id == str(ncrm_id))
            if not results:
                print_error(f"NCRM entry '{ncrm_id}' not found.")
                return None
            entry = results[0]
            updates = data.model_dump(exclude_none=True)
            if "smiles" in updates and updates["smiles"]:
                canonical = canonicalize_smiles(updates["smiles"])
                updates["smiles"] = canonical or updates["smiles"]
            await entry.update_fields(session, **updates)
            return entry
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update NCRM entry: {exc}")
        return None


async def delete_ncrm_library_entry(
    ncrm_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete an NCRM library entry by UUID.

    Args:
        ncrm_id: UUID of the NCRM entry to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await NcrmLibrary.get_where(session, NcrmLibrary.id == str(ncrm_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete NCRM entry: {exc}")
        return False


async def add_ncrm_alias(
    data: NcrmLibraryAliasCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibraryAlias | None:
    """Add an alias to an existing NCRM library entry.

    Args:
        data: Validated :class:`~..schema.create.NcrmLibraryAliasCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.NcrmLibraryAlias`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            alias = NcrmLibraryAlias(ncrm_library_id=str(data.ncrm_library_id), alias=data.alias)
            session.add(alias)
            await session.commit()
            await session.refresh(alias)
            return alias
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to add NCRM alias: {exc}")
        return None
