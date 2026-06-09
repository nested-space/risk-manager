"""
Material CRUD, search, and bulk import operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Material, MaterialAlias
from ..schema.create import MaterialAliasCreate, MaterialCreate
from ..schema.update import MaterialUpdate
from ..utils.console_formatting import print_error, print_success, print_warning
from ..utils.parsing import parse_csv_rows, split_aliases
from .smiles_operations import (
    canonicalize_smiles,
    detect_search_type,
    is_valid_smiles,
)


async def create_material(
    data: MaterialCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Material | None:
    """Create a new material record.

    Validates and canonicalizes the SMILES if provided.

    Args:
        data: Validated :class:`~..schema.create.MaterialCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.Material`; ``None`` on error.
    """
    try:
        smiles: str | None = None
        if data.smiles:
            if not is_valid_smiles(data.smiles):
                print_error(f"Invalid SMILES for material '{data.name}': {data.smiles}")
                return None
            smiles = canonicalize_smiles(data.smiles) or data.smiles

        async with get_db_session(env, verbose) as session:
            material = Material(name=data.name, smiles=smiles)
            session.add(material)
            await session.commit()
            await session.refresh(material)
            print_success(f"Created material '{material.name}'.")
            return material
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create material: {exc}")
        return None


async def get_material_by_id(
    material_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Material | None:
    """Retrieve a material by UUID.

    Args:
        material_id: UUID of the material.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Material`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Material.get_where(session, Material.id == str(material_id))
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get material by ID: {exc}")
        return None


async def get_material_by_name(
    name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Material | None:
    """Retrieve a material by exact name.

    Args:
        name: Exact material name.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Material`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Material.get_where(session, Material.name == name)
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get material by name: {exc}")
        return None


async def get_material_by_smiles(
    smiles: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Material | None:
    """Retrieve a material by SMILES string (canonical form).

    Args:
        smiles: SMILES string (will be canonicalized before lookup).
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Material`; ``None`` if not found.
    """
    canonical = canonicalize_smiles(smiles) or smiles
    try:
        async with get_db_session(env, verbose) as session:
            results = await Material.get_where(session, Material.smiles == canonical)
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get material by SMILES: {exc}")
        return None


async def get_material_by_search(
    search_value: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Material | None:
    """Search for a material by ID, name, or SMILES with auto-detection.

    Why this exists:
        Different contexts provide different identifiers — UUIDs from exports,
        SMILES from chemical searches, names from user input. Auto-detection
        eliminates the need for explicit type specification in most cases.

    Args:
        search_value: An identifier string (UUID, SMILES, or name).
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Material`; ``None`` if not found.
    """
    search_type = detect_search_type(search_value)
    if search_type == "id":
        return await get_material_by_id(UUID(search_value), env, verbose)
    if search_type == "smiles":
        return await get_material_by_smiles(search_value, env, verbose)
    return await get_material_by_name(search_value, env, verbose)


async def list_materials(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Material]:
    """Return all materials ordered by name.

    Args:
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.Material` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Material.get_all(session)
            return sorted(results, key=lambda m: m.name)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list materials: {exc}")
        return []


async def update_material(
    material_id: UUID,
    data: MaterialUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Material | None:
    """Update fields on an existing material.

    Args:
        material_id: UUID of the material to update.
        data: Validated :class:`~..schema.update.MaterialUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.Material`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Material.get_where(session, Material.id == str(material_id))
            if not results:
                print_error(f"Material '{material_id}' not found.")
                return None
            material = results[0]
            updates = data.model_dump(exclude_none=True)
            if "smiles" in updates and updates["smiles"]:
                canonical = canonicalize_smiles(updates["smiles"])
                updates["smiles"] = canonical or updates["smiles"]
            await material.update_fields(session, **updates)
            return material
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update material: {exc}")
        return None


async def delete_material(
    material_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a material by UUID.

    Args:
        material_id: UUID of the material to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Material.get_where(session, Material.id == str(material_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete material: {exc}")
        return False


async def add_material_alias(
    data: MaterialAliasCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> MaterialAlias | None:
    """Add an alias to an existing material.

    Args:
        data: Validated :class:`~..schema.create.MaterialAliasCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.MaterialAlias`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            alias = MaterialAlias(material_id=str(data.material_id), alias=data.alias)
            session.add(alias)
            await session.commit()
            await session.refresh(alias)
            return alias
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to add material alias: {exc}")
        return None


async def bulk_import_materials(
    csv_content: str,
    env: Environment = Environment.DEV,
    skip_errors: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, int]:
    """Bulk-import materials from CSV content.

    CSV format: ``name,smiles,aliases`` (aliases semicolon-separated).

    Args:
        csv_content: Full CSV file content as a UTF-8 string.
        env: Database environment.
        skip_errors: If ``True``, log row errors and continue; otherwise abort.
        dry_run: If ``True``, validate rows without writing to the database.
        verbose: If ``True``, prints the database path.

    Returns:
        A dict with keys ``"created"``, ``"skipped"``, ``"errors"``.
    """
    counts: dict[str, int] = {"created": 0, "skipped": 0, "errors": 0}
    for row in parse_csv_rows(csv_content):
        name = row.get("name", "").strip()
        if not name:
            print_warning("Skipping row with missing 'name' field.")
            counts["skipped"] += 1
            continue

        smiles_raw = row.get("smiles", "").strip() or None
        aliases_raw = row.get("aliases", "").strip()

        if dry_run:
            print_warning(f"[DRY RUN] Would create material '{name}'.")
            counts["created"] += 1
            continue

        result = await create_material(MaterialCreate(name=name, smiles=smiles_raw), env, verbose)
        if result is None:
            counts["errors"] += 1
            if not skip_errors:
                return counts
        else:
            counts["created"] += 1
            for alias in split_aliases(aliases_raw):
                await add_material_alias(
                    MaterialAliasCreate(material_id=UUID(str(result.id)), alias=alias),
                    env,
                    verbose,
                )

    return counts
