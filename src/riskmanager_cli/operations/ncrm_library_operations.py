"""
NCRM library CRUD and search operations.

All functions are ``async def`` and open their own database sessions. On error,
they log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The
common CRUD shapes delegate to the ``generic_*`` helpers in
:mod:`.base_operations`; only NCRM-specific logic lives here.
"""

from collections import Counter
from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import NcrmLibrary, NcrmLibraryAlias
from ..schema.create import NcrmLibraryAliasCreate, NcrmLibraryCreate
from ..schema.update import NcrmLibraryUpdate
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


@db_operation(default=None, error="Failed to create NCRM entry")
async def create_ncrm_library_entry(
    data: NcrmLibraryCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibrary | None:
    """Create a new NCRM library entry, validating/canonicalizing any SMILES.

    Args:
        data: Validated :class:`~..schema.create.NcrmLibraryCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.NcrmLibrary`; ``None`` on error.
    """
    smiles: str | None = None
    if data.smiles:
        if not is_valid_smiles(data.smiles):
            print_error(f"Invalid SMILES for NCRM '{data.name}': {data.smiles}")
            return None
        smiles = canonicalize_smiles(data.smiles) or data.smiles

    display_name = data.display_name or data.name
    entry = NcrmLibrary(
        display_name=display_name,
        name=data.name,
        interpret_chemically=data.interpret_chemically,
        smiles=smiles,
    )
    return await generic_create(
        entry, "NCRM entry", env, verbose, success_message=f"Created NCRM entry '{display_name}'."
    )


async def get_ncrm_by_id(
    ncrm_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibrary | None:
    """Retrieve an NCRM library entry by UUID; ``None`` if not found."""
    return await generic_get_by_id(NcrmLibrary, ncrm_id, "NCRM entry", env, verbose)


@db_operation(default=None, error="Failed to get NCRM entry by display name")
async def get_ncrm_by_display_name(
    display_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibrary | None:
    """Retrieve an NCRM library entry by its display name; ``None`` if not found."""
    async with get_db_session(env, verbose) as session:
        results = await NcrmLibrary.get_where(session, NcrmLibrary.display_name == display_name)
        return results[0] if results else None


async def list_ncrm_library(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[NcrmLibrary]:
    """Return all NCRM library entries ordered by display name."""
    return await generic_list(
        NcrmLibrary, "NCRM library", env, verbose, sort_key=lambda n: n.display_name
    )


@db_operation(default={}, error="Failed to count NCRM aliases")
async def ncrm_alias_counts(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> dict[str, int]:
    """Return a mapping of NCRM library entry id to its alias count.

    Entries with no aliases are absent from the mapping.
    """
    async with get_db_session(env, verbose) as session:
        aliases = await NcrmLibraryAlias.get_all(session)
        return dict(Counter(str(alias.ncrm_library_id) for alias in aliases))


@db_operation(default=[], error="Failed to list NCRM aliases")
async def list_ncrm_aliases(
    ncrm_library_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[str]:
    """Return the aliases of a single NCRM library entry, sorted case-insensitively."""
    async with get_db_session(env, verbose) as session:
        aliases = await NcrmLibraryAlias.get_where(
            session, NcrmLibraryAlias.ncrm_library_id == str(ncrm_library_id)
        )
        return sorted((alias.alias for alias in aliases), key=str.casefold)


async def update_ncrm_library_entry(
    ncrm_id: UUID,
    data: NcrmLibraryUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibrary | None:
    """Update fields on an existing NCRM library entry; ``None`` on not-found or error."""
    updates = data.model_dump(exclude_none=True)
    if updates.get("smiles"):
        updates["smiles"] = canonicalize_smiles(updates["smiles"]) or updates["smiles"]
    return await generic_update(
        NcrmLibrary,
        ncrm_id,
        "NCRM entry",
        updates,
        env=env,
        verbose=verbose,
        not_found_label="NCRM entry",
    )


async def delete_ncrm_library_entry(
    ncrm_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete an NCRM library entry by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(NcrmLibrary, ncrm_id, "NCRM entry", env, verbose)


async def add_ncrm_alias(
    data: NcrmLibraryAliasCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> NcrmLibraryAlias | None:
    """Add an alias to an existing NCRM library entry; ``None`` on error."""
    alias = NcrmLibraryAlias(ncrm_library_id=str(data.ncrm_library_id), alias=data.alias)
    return await generic_create(alias, "NCRM alias", env, verbose)
