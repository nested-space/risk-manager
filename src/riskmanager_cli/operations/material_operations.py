"""
Material CRUD, search, and bulk import operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from collections import Counter
from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Material, MaterialAlias
from ..schema.create import MaterialAliasCreate, MaterialCreate
from ..schema.update import MaterialUpdate
from ..utils.console_formatting import print_error, print_success, print_warning
from ..utils.parsing import parse_csv_rows, split_aliases
from .dmta_operations import augment_name
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
            material = Material(
                name=data.name,
                display_name=data.display_name or data.name,
                interpret_chemically=data.interpret_chemically,
                smiles=smiles,
            )
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


async def material_alias_counts(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> dict[str, int]:
    """Return a mapping of material id to its alias count.

    Args:
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        A ``dict`` keyed by material id string; materials with no aliases are
        absent. Empty ``dict`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            aliases = await MaterialAlias.get_all(session)
            return dict(Counter(str(alias.material_id) for alias in aliases))
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to count material aliases: {exc}")
        return {}


async def list_material_aliases(
    material_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[str]:
    """Return the aliases of a single material, sorted case-insensitively.

    Args:
        material_id: UUID of the material whose aliases to list.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The alias strings in case-insensitive order; empty on error or when the
        material has none.
    """
    try:
        async with get_db_session(env, verbose) as session:
            aliases = await MaterialAlias.get_where(
                session, MaterialAlias.material_id == str(material_id)
            )
            return sorted((alias.alias for alias in aliases), key=str.casefold)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list material aliases: {exc}")
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

    CSV format: ``name,display_name,interpret_chemically,smiles,aliases``
    (aliases semicolon-separated). Only ``name`` is required: ``display_name``
    defaults to ``name`` and ``interpret_chemically`` defaults to ``false`` when
    their columns are absent, so legacy ``name,smiles,aliases`` files still import.

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
        display_name = row.get("display_name", "").strip() or None
        interpret_chemically = row.get("interpret_chemically", "").strip().lower() == "true"

        if dry_run:
            print_warning(f"[DRY RUN] Would create material '{name}'.")
            counts["created"] += 1
            continue

        result = await create_material(
            MaterialCreate(
                name=name,
                display_name=display_name,
                interpret_chemically=interpret_chemically,
                smiles=smiles_raw,
            ),
            env,
            verbose,
        )
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


async def existing_display_names(
    exclude_id: UUID | None = None,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[str]:
    """Return names already in use by materials, for display-name collision checks.

    Gathers every material's ``name`` and ``display_name`` plus all aliases, so a
    suggested display name can be disambiguated against the existing set.

    Args:
        exclude_id: Material to omit (the one being edited), or ``None``.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The names, display names, and aliases in use; empty on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            materials = await Material.get_all(session)
            aliases = await MaterialAlias.get_all(session)
        names: list[str] = []
        for material in materials:
            if exclude_id is not None and str(material.id) == str(exclude_id):
                continue
            names.append(material.name)
            names.append(material.display_name)
        names.extend(alias.alias for alias in aliases)
        return names
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to gather existing display names: {exc}")
        return []


async def display_name_is_unambiguous(
    display_name: str,
    own_smiles: str | None,
) -> bool | None:
    """Check that *display_name* does not resolve to a *different* known compound.

    Why this exists:
        A shortened display name should not coincide with a registry/PubChem
        synonym for an unrelated structure. This best-effort check resolves the
        candidate name and compares the resulting structure with the material's
        own SMILES.

    Args:
        display_name: The candidate short display name.
        own_smiles: The material's canonical SMILES, or ``None`` when unknown.

    Returns:
        ``True`` when the name resolves to the same structure (or harmlessly),
        ``False`` when it resolves to a different compound, and ``None`` when no
        determination is possible (no SMILES to compare, offline, or unresolved).
    """
    if not own_smiles:
        return None
    result = await augment_name(display_name)
    if not result.resolved or not result.smiles:
        return None
    resolved = canonicalize_smiles(result.smiles) or result.smiles
    own = canonicalize_smiles(own_smiles) or own_smiles
    return resolved == own
