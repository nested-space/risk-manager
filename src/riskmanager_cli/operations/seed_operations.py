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
from ..model.tables import Counterion, CounterionAlias, NcrmLibrary, NcrmLibraryAlias
from .smiles_operations import canonicalize_smiles, is_valid_smiles

COUNTERION_SEED_FILE = "counterions.json"
NCRM_SEED_FILE = "ncrm.json"

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
