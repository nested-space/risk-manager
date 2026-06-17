"""First-run seeding of the default counterion and NCRM reference libraries.

Loads the curated reference data committed under ``data/seed/*.json`` and
bulk-inserts it into a freshly created database. Unlike the per-row
``create_counterion`` / ``create_ncrm_library_entry`` operations (each of which
opens its own engine and prints a success line), these functions:

* open a **single** session and commit once, so seeding ~350 rows at startup is
  fast and does not churn engines;
* stay **silent** (no ``print_success`` per row) and instead report progress via
  an optional callback, so the bootstrap screen can render a live counter;
* isolate each row in a SAVEPOINT (``begin_nested``) so a single bad row — for
  example a SMILES that collides with the unique constraint — is counted and
  skipped without aborting the whole batch.

Why this exists:
    A brand-new database is useless until the reference libraries are loaded.
    Seeding them automatically on first run removes a mandatory manual import
    step for every new user. See :mod:`~riskmanager_cli.repl.bootstrap` for the
    first-run detection and progress UI that drive these operations.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from importlib import resources
from typing import TypedDict, cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.enums import TA, NcrmRole
from ..model.tables import (
    Component,
    Counterion,
    CounterionAlias,
    ManufacturingProcess,
    Material,
    MaterialAlias,
    NcrmLibrary,
    NcrmLibraryAlias,
    Project,
    Stage,
    StageComponent,
    StageNcrm,
)
from .smiles_operations import canonicalize_smiles, is_valid_smiles

COUNTERION_SEED_FILE = "counterions.json"
NCRM_SEED_FILE = "ncrm.json"
EXAMPLE_PROJECT_SEED_FILE = "example_project.json"
OSIMERTINIB_PROJECT_SEED_FILE = "example_project_osimertinib.json"
# Every committed example-project seed, loaded in order during first-run bootstrap.
EXAMPLE_PROJECT_SEED_FILES = (EXAMPLE_PROJECT_SEED_FILE, OSIMERTINIB_PROJECT_SEED_FILE)

ProgressCallback = Callable[[int, int], None]


class SeedEntry(TypedDict):
    """One reference-library row as stored in the committed JSON seed files.

    Attributes:
        name: Unique chemical name.
        display_name: Short label shown in listings; falls back to ``name``.
        interpret_chemically: Whether the SMILES is semantically interpreted.
        smiles: Optional SMILES notation (``None`` when absent).
        aliases: Alternative names / identifiers for the entry.
    """

    name: str
    display_name: str
    interpret_chemically: bool
    smiles: str | None
    aliases: list[str]


def load_seed_entries(filename: str) -> list[SeedEntry]:
    """Load and parse a committed JSON seed file shipped inside the package.

    Args:
        filename: Bare file name under ``riskmanager_cli/data/seed`` (e.g.
            :data:`COUNTERION_SEED_FILE`).

    Returns:
        The parsed list of :class:`SeedEntry` rows.
    """
    resource = resources.files("riskmanager_cli.data.seed").joinpath(filename)
    with resource.open("r", encoding="utf-8") as handle:
        return cast("list[SeedEntry]", json.load(handle))


def _resolve_smiles(raw: str | None) -> tuple[bool, str | None]:
    """Validate and canonicalize a seed SMILES string.

    Args:
        raw: SMILES value from the seed entry, possibly ``None`` or blank.

    Returns:
        A ``(valid, smiles)`` pair. ``valid`` is ``False`` only when a non-empty
        SMILES fails validation; ``smiles`` is the canonical form, or ``None``
        when absent or invalid.
    """
    value = (raw or "").strip()
    if not value:
        return True, None
    if not is_valid_smiles(value):
        return False, None
    return True, canonicalize_smiles(value) or value


async def _insert_with_savepoint(
    session: AsyncSession,
    parent: SQLModel,
    alias_rows: list[SQLModel],
) -> bool:
    """Insert a parent row and its aliases inside a single SAVEPOINT.

    Args:
        session: The open session shared across the whole seeding batch.
        parent: The parent record (a :class:`Counterion` or :class:`NcrmLibrary`).
        alias_rows: Alias records already pointing at ``parent``'s id.

    Returns:
        ``True`` on success; ``False`` if the row violated a constraint (the
        SAVEPOINT is rolled back, leaving the outer transaction usable).
    """
    try:
        async with session.begin_nested():
            session.add(parent)
            await session.flush()
            for row in alias_rows:
                session.add(row)
            if alias_rows:
                await session.flush()
    except Exception:  # pylint: disable=broad-except  # one bad row must not abort the batch
        return False
    return True


async def _seed_counterion_row(session: AsyncSession, entry: SeedEntry) -> str:
    """Seed one counterion plus its aliases; return the outcome bucket name."""
    name = entry["name"].strip()
    if not name:
        return "skipped"
    valid, smiles = _resolve_smiles(entry["smiles"])
    if not valid:
        return "errors"
    parent = Counterion(
        name=name,
        display_name=entry["display_name"].strip() or name,
        interpret_chemically=entry["interpret_chemically"],
        smiles=smiles,
    )
    alias_rows: list[SQLModel] = [
        CounterionAlias(counterion_id=str(parent.id), alias=alias.strip())
        for alias in entry["aliases"]
        if alias.strip()
    ]
    return "created" if await _insert_with_savepoint(session, parent, alias_rows) else "errors"


async def _seed_ncrm_row(session: AsyncSession, entry: SeedEntry) -> str:
    """Seed one NCRM library entry plus its aliases; return the outcome bucket name."""
    name = entry["name"].strip()
    if not name:
        return "skipped"
    valid, smiles = _resolve_smiles(entry["smiles"])
    if not valid:
        return "errors"
    parent = NcrmLibrary(
        name=name,
        display_name=entry["display_name"].strip() or name,
        interpret_chemically=entry["interpret_chemically"],
        smiles=smiles,
    )
    alias_rows: list[SQLModel] = [
        NcrmLibraryAlias(ncrm_library_id=str(parent.id), alias=alias.strip())
        for alias in entry["aliases"]
        if alias.strip()
    ]
    return "created" if await _insert_with_savepoint(session, parent, alias_rows) else "errors"


async def _run_seed(
    entries: list[SeedEntry],
    env: Environment,
    progress: ProgressCallback | None,
    row_seeder: Callable[[AsyncSession, SeedEntry], Awaitable[str]],
) -> dict[str, int]:
    """Drive a seeding batch over *entries* using *row_seeder*.

    Opens a single session, seeds each row (reporting progress after each), and
    commits once at the end.

    Args:
        entries: Rows to seed.
        env: Database environment.
        progress: Optional callback invoked as ``progress(done, total)`` after
            every row, including skipped/errored ones.
        row_seeder: Coroutine that inserts one row and returns its outcome bucket
            (``"created"``, ``"skipped"`` or ``"errors"``).

    Returns:
        A dict with keys ``"created"``, ``"skipped"``, ``"errors"``.
    """
    counts = {"created": 0, "skipped": 0, "errors": 0}
    total = len(entries)
    async with get_db_session(env) as session:
        for index, entry in enumerate(entries, start=1):
            counts[await row_seeder(session, entry)] += 1
            if progress is not None:
                progress(index, total)
        await session.commit()
    return counts


async def seed_counterions(
    entries: list[SeedEntry],
    env: Environment = Environment.DEV,
    progress: ProgressCallback | None = None,
) -> dict[str, int]:
    """Bulk-seed counterions (with aliases) into the database.

    Args:
        entries: Counterion rows, typically from :func:`load_seed_entries`.
        env: Database environment.
        progress: Optional ``progress(done, total)`` callback.

    Returns:
        A dict with keys ``"created"``, ``"skipped"``, ``"errors"``.
    """
    return await _run_seed(entries, env, progress, _seed_counterion_row)


async def seed_ncrm(
    entries: list[SeedEntry],
    env: Environment = Environment.DEV,
    progress: ProgressCallback | None = None,
) -> dict[str, int]:
    """Bulk-seed NCRM library entries (with aliases) into the database.

    Args:
        entries: NCRM rows, typically from :func:`load_seed_entries`.
        env: Database environment.
        progress: Optional ``progress(done, total)`` callback.

    Returns:
        A dict with keys ``"created"``, ``"skipped"``, ``"errors"``.
    """
    return await _run_seed(entries, env, progress, _seed_ncrm_row)


# ---------------------------------------------------------------------------
# Example project seeding
# ---------------------------------------------------------------------------


class ProjectSeedMaterial(TypedDict):
    """One material (API, starting material or intermediate) in the example project.

    Attributes:
        name: Unique material name.
        display_name: Short label; falls back to ``name`` when blank.
        interpret_chemically: Whether the SMILES is semantically interpreted.
        smiles: Optional SMILES notation (``None`` when absent).
        aliases: Alternative names / identifiers (IUPAC name, CAS, etc.).
        control_strategy_role: Role label in the process (``API``/``RSM``/``INT``).
        is_isolated: Whether the material is isolated within the process.
    """

    name: str
    display_name: str
    interpret_chemically: bool
    smiles: str | None
    aliases: list[str]
    control_strategy_role: str | None
    is_isolated: bool


class ProjectSeedNcrm(TypedDict):
    """One non-contributory raw material reference within a stage.

    Attributes:
        name: NCRM name; resolved case-insensitively against the seeded library.
        role: NCRM role value matching :class:`~..model.enums.NcrmRole`.
    """

    name: str
    role: str


class ProjectSeedStage(TypedDict):
    """One manufacturing stage of the example project.

    Attributes:
        number: Stage sequence number (unique within the process).
        name: Stage name (carries the original branch/stage label).
        reactants: Material names consumed in the stage.
        products: Material names produced in the stage.
        ncrms: NCRM references used in the stage.
    """

    number: int
    name: str
    reactants: list[str]
    products: list[str]
    ncrms: list[ProjectSeedNcrm]


class ProjectSeedMeta(TypedDict):
    """Top-level metadata for the example project.

    Attributes:
        name: Project name.
        therapy_area: Therapy area value matching :class:`~..model.enums.TA`.
        route_number: Route identifier within the project.
        process_number: Process identifier within the route.
        api_material: Name of the material that is the project's API.
    """

    name: str
    therapy_area: str
    route_number: int
    process_number: int
    api_material: str


class ExampleProjectSeed(TypedDict):
    """The full example-project seed graph as stored in ``example_project.json``.

    Attributes:
        project: Project-level metadata.
        materials: Materials (API, starting materials, intermediates).
        stages: Manufacturing stages with their reactant/product/NCRM links.
    """

    project: ProjectSeedMeta
    materials: list[ProjectSeedMaterial]
    stages: list[ProjectSeedStage]


def load_example_project(filename: str = EXAMPLE_PROJECT_SEED_FILE) -> ExampleProjectSeed:
    """Load and parse a committed example-project seed shipped in the package.

    Args:
        filename: Bare file name under ``riskmanager_cli/data/seed`` (one of
            :data:`EXAMPLE_PROJECT_SEED_FILES`). Defaults to the ibuprofen seed.

    Returns:
        The parsed :class:`ExampleProjectSeed` graph.
    """
    resource = resources.files("riskmanager_cli.data.seed").joinpath(filename)
    with resource.open("r", encoding="utf-8") as handle:
        return cast("ExampleProjectSeed", json.load(handle))


async def _seed_project_material(
    session: AsyncSession,
    entry: ProjectSeedMaterial,
    material_ids: dict[str, str],
) -> str:
    """Seed one material plus its aliases; record its id and return the outcome bucket."""
    name = entry["name"].strip()
    if not name:
        return "skipped"
    valid, smiles = _resolve_smiles(entry["smiles"])
    if not valid:
        return "errors"
    parent = Material(
        name=name,
        display_name=entry["display_name"].strip() or name,
        interpret_chemically=entry["interpret_chemically"],
        smiles=smiles,
    )
    alias_rows: list[SQLModel] = [
        MaterialAlias(material_id=str(parent.id), alias=alias.strip())
        for alias in entry["aliases"]
        if alias.strip()
    ]
    if await _insert_with_savepoint(session, parent, alias_rows):
        material_ids[name] = str(parent.id)
        return "created"
    return "errors"


async def _seed_project_skeleton(
    session: AsyncSession,
    data: ExampleProjectSeed,
    material_ids: dict[str, str],
) -> tuple[str | None, dict[str, str]]:
    """Create the project, its process and one component per material.

    Args:
        session: The open session shared across the seeding batch.
        data: The full example-project seed graph.
        material_ids: Mapping of material name to id from the materials phase.

    Returns:
        A ``(process_id, component_ids)`` pair. ``process_id`` is ``None`` when
        the project or process could not be created (e.g. the API material was
        missing); ``component_ids`` maps material name to its component id.
    """
    meta = data["project"]
    api_id = material_ids.get(meta["api_material"].strip())
    if api_id is None:
        return None, {}
    project = Project(name=meta["name"], therapy_area=TA(meta["therapy_area"]), material_id=api_id)
    if not await _insert_with_savepoint(session, project, []):
        return None, {}
    process = ManufacturingProcess(
        project_id=str(project.id),
        route_number=meta["route_number"],
        process_number=meta["process_number"],
    )
    if not await _insert_with_savepoint(session, process, []):
        return None, {}
    process_id = str(process.id)
    component_ids: dict[str, str] = {}
    for entry in data["materials"]:
        material_id = material_ids.get(entry["name"].strip())
        if material_id is None:
            continue
        component = Component(
            process_id=process_id,
            material_id=material_id,
            control_strategy_role=entry["control_strategy_role"],
            is_isolated=entry["is_isolated"],
        )
        if await _insert_with_savepoint(session, component, []):
            component_ids[entry["name"].strip()] = str(component.id)
    return process_id, component_ids


def _stage_links(
    stage_id: str,
    entry: ProjectSeedStage,
    component_ids: dict[str, str],
    ncrm_by_name: dict[str, str],
) -> list[SQLModel]:
    """Build the stage-component and stage-NCRM link rows for one stage."""
    links: list[SQLModel] = []
    for material_name in entry["reactants"]:
        component_id = component_ids.get(material_name)
        if component_id is not None:
            links.append(
                StageComponent(
                    stage_id=stage_id, component_id=component_id, component_type="reactant"
                )
            )
    for material_name in entry["products"]:
        component_id = component_ids.get(material_name)
        if component_id is not None:
            links.append(
                StageComponent(
                    stage_id=stage_id, component_id=component_id, component_type="product"
                )
            )
    for ncrm in entry["ncrms"]:
        ncrm_id = ncrm_by_name.get(ncrm["name"].casefold())
        if ncrm_id is not None:
            links.append(StageNcrm(ncrm_id=ncrm_id, stage_id=stage_id, role=NcrmRole(ncrm["role"])))
    return links


async def _seed_project_stage(
    session: AsyncSession,
    entry: ProjectSeedStage,
    process_id: str | None,
    component_ids: dict[str, str],
    ncrm_by_name: dict[str, str],
) -> str:
    """Seed one stage plus its component and NCRM links; return the outcome bucket."""
    if process_id is None:
        return "errors"
    stage = Stage(process_id=process_id, name=entry["name"].strip(), number=entry["number"])
    if not await _insert_with_savepoint(session, stage, []):
        return "errors"
    for link in _stage_links(str(stage.id), entry, component_ids, ncrm_by_name):
        await _insert_with_savepoint(session, link, [])
    return "created"


async def seed_example_project(
    data: ExampleProjectSeed,
    env: Environment = Environment.DEV,
    progress: ProgressCallback | None = None,
) -> dict[str, int]:
    """Seed the example project graph (materials, process, stages, links).

    NCRM references are resolved against the already-seeded NCRM library, so this
    must run after :func:`seed_ncrm`. Each row is isolated in a SAVEPOINT so a
    single bad row is skipped without aborting the batch.

    Args:
        data: The example-project seed graph, from :func:`load_example_project`.
        env: Database environment.
        progress: Optional ``progress(done, total)`` callback, invoked once per
            material and once per stage; ``total`` is materials + stages.

    Returns:
        A dict with keys ``"created"``, ``"skipped"``, ``"errors"`` counting the
        materials and stages processed.
    """
    counts = {"created": 0, "skipped": 0, "errors": 0}
    materials = data["materials"]
    stages = data["stages"]
    total = len(materials) + len(stages)
    done = 0
    async with get_db_session(env) as session:
        ncrm_by_name = {
            row.name.casefold(): str(row.id) for row in await NcrmLibrary.get_all(session)
        }
        material_ids: dict[str, str] = {}
        for material in materials:
            counts[await _seed_project_material(session, material, material_ids)] += 1
            done += 1
            if progress is not None:
                progress(done, total)
        process_id, component_ids = await _seed_project_skeleton(session, data, material_ids)
        for stage in stages:
            counts[
                await _seed_project_stage(session, stage, process_id, component_ids, ncrm_by_name)
            ] += 1
            done += 1
            if progress is not None:
                progress(done, total)
        await session.commit()
    return counts
