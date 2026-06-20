"""
Generic base operation helpers shared across all entity operations modules.

Provides the session/error scaffolding that every entity operation needs, so
the per-entity modules carry only their own specialised logic:

* :func:`db_operation` — a decorator that absorbs exceptions, logs via
  ``print_error``, and returns a default. It is the **single** home for the
  operations layer's ``broad-except`` (see ``AGENTS.md`` §5).
* ``generic_*`` — typed CRUD helpers (get-by-id, existence, stats, delete,
  list, create, update) that entity modules delegate to instead of hand-rolling
  the ``try → async with get_db_session → query → except → return default``
  shape.

Why this exists:
    The 16 entity operations modules all follow identical patterns for the
    common CRUD shapes. Centralising them here removes the duplicated
    session/error boilerplate while keeping each entity module focused on its
    own field mapping and validation.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import CRUDMixin
from ..utils.console_formatting import print_error, print_success

# Type alias: a callable that computes stats from a list of model instances.
StatsCalculator = Callable[[list[Any]], dict[str, Any]]

M = TypeVar("M", bound=CRUDMixin)
R = TypeVar("R")
D = TypeVar("D")
P = ParamSpec("P")
T = TypeVar("T")


async def _guarded(error: str, default: D, factory: Callable[[], Awaitable[R]]) -> R | D:
    """Run *factory*, returning *default* (and logging) if it raises.

    This is the one place in the operations layer that catches a bare
    ``Exception``: every operation absorbs errors, logs them, and returns a
    sentinel default rather than propagating (``AGENTS.md`` §5).

    Args:
        error: Message prefix logged before the exception detail.
        default: Value returned when *factory* raises.
        factory: Zero-argument callable returning the operation's coroutine.

    Returns:
        The factory's result, or *default* on any exception.
    """
    try:
        return await factory()
    # broad-except is intentional and lives only here: operations absorb all
    # errors, log via print_error, and return a default (AGENTS.md §5).
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"{error}: {exc}")
        return default


def db_operation(
    default: object, *, error: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap an operation so exceptions are logged and *default* is returned.

    Use on entity operations whose error message is static (e.g. create, add
    alias, bespoke lookups). The decorated function keeps its own signature and
    opens its own session; this decorator only supplies the shared
    error-handling path via :func:`_guarded`.

    *default* is typed ``object`` (not the return type) so the wrapped
    function's annotation drives the decorated signature; the caller supplies a
    sentinel that is a valid instance of that return type (``None`` / ``[]`` /
    ``{}`` / ``False``), which is cast back to it.

    Args:
        default: Sentinel returned when the wrapped coroutine raises.
        error: Static message prefix logged before the exception detail.

    Returns:
        A decorator preserving the wrapped function's parameters and return type.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await _guarded(error, cast(T, default), lambda: func(*args, **kwargs))

        return wrapper

    return decorator


def _id_column(model_class: type[CRUDMixin]) -> Any:
    """Return the SQLAlchemy ``id`` column expression for *model_class*."""
    return getattr(model_class, "id")


async def _rows_for_id(model_class: type[M], session: AsyncSession, entity_id: UUID) -> list[M]:
    """Return the rows of *model_class* whose primary key equals *entity_id*."""
    return await model_class.get_where(session, _id_column(model_class) == str(entity_id))


async def generic_get_by_id(
    model_class: type[M],
    entity_id: UUID,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> M | None:
    """Retrieve any entity by UUID primary key.

    Args:
        model_class: The SQLModel table class to query.
        entity_id: UUID of the entity to retrieve.
        entity_name: Human-readable label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.

    Returns:
        The model instance if found; ``None`` on not-found or error.
    """

    async def _op() -> M | None:
        async with get_db_session(env, verbose) as session:
            results = await _rows_for_id(model_class, session, entity_id)
            return results[0] if results else None

    return await _guarded(f"Failed to get {entity_name} by ID", None, _op)


async def generic_check_exists(
    model_class: type[M],
    entity_id: UUID,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Return whether an entity exists by UUID; ``False`` on error.

    Args:
        model_class: The SQLModel table class to query.
        entity_id: UUID to look up.
        entity_name: Human-readable label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.

    Returns:
        ``True`` if the entity exists; ``False`` otherwise.
    """

    async def _op() -> bool:
        async with get_db_session(env, verbose) as session:
            results = await _rows_for_id(model_class, session, entity_id)
            return len(results) > 0

    return await _guarded(f"Failed to check {entity_name} existence", False, _op)


async def generic_get_stats(
    model_class: type[M],
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
    stats_calculator: StatsCalculator | None = None,
) -> dict[str, Any]:
    """Return statistics for an entity type, always including ``"total"``.

    Args:
        model_class: The SQLModel table class to query.
        entity_name: Human-readable label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.
        stats_calculator: Optional callable that receives all records and
            returns a ``dict`` of additional statistics.

    Returns:
        A dict with at least ``{"total": N}``, or ``{"total": 0}`` on error.
    """

    async def _op() -> dict[str, Any]:
        async with get_db_session(env, verbose) as session:
            entities = await model_class.get_all(session)
            base: dict[str, Any] = {"total": len(entities)}
            if stats_calculator:
                base.update(stats_calculator(entities))
            return base

    return await _guarded(f"Failed to get {entity_name} stats", {"total": 0}, _op)


async def generic_delete_by_id(
    model_class: type[M],
    entity_id: UUID,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete an entity by UUID primary key.

    Args:
        model_class: The SQLModel table class to query.
        entity_id: UUID of the entity to delete.
        entity_name: Human-readable label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.

    Returns:
        ``True`` if found and deleted; ``False`` on not-found or error.
    """

    async def _op() -> bool:
        async with get_db_session(env, verbose) as session:
            results = await _rows_for_id(model_class, session, entity_id)
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True

    return await _guarded(f"Failed to delete {entity_name}", False, _op)


async def generic_list(
    model_class: type[M],
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
    *,
    sort_key: Callable[[M], Any] | None = None,
) -> list[M]:
    """Return all records of *model_class*, optionally sorted by *sort_key*.

    Args:
        model_class: The SQLModel table class to query.
        entity_name: Human-readable label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.
        sort_key: Optional key function applied to sort the results.

    Returns:
        The records (sorted when *sort_key* is given); empty list on error.
    """

    async def _op() -> list[M]:
        async with get_db_session(env, verbose) as session:
            results = await model_class.get_all(session)
            return sorted(results, key=sort_key) if sort_key is not None else results

    empty: list[M] = []
    return await _guarded(f"Failed to list {entity_name}", empty, _op)


async def generic_create(
    instance: M,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
    *,
    success_message: str | None = None,
) -> M | None:
    """Persist a pre-built model *instance*, returning it (refreshed).

    The caller builds and validates *instance* (field mapping, SMILES
    canonicalisation); this helper owns only the session/commit/error path.

    Args:
        instance: The unsaved model instance to add.
        entity_name: Human-readable label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.
        success_message: Optional message printed via ``print_success`` on commit.

    Returns:
        The persisted, refreshed instance; ``None`` on error.
    """

    async def _op() -> M:
        async with get_db_session(env, verbose) as session:
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            if success_message:
                print_success(success_message)
            return instance

    return await _guarded(f"Failed to create {entity_name}", None, _op)


async def generic_update(  # pylint: disable=too-many-arguments  # env/verbose pair exceeds arg cap
    model_class: type[M],
    entity_id: UUID,
    entity_name: str,
    updates: dict[str, Any],
    *,
    env: Environment = Environment.DEV,
    verbose: bool = False,
    not_found_label: str | None = None,
) -> M | None:
    """Apply *updates* to the entity with *entity_id*.

    Args:
        model_class: The SQLModel table class to update.
        entity_id: UUID of the entity to update.
        entity_name: Human-readable label used in the "failed" error message.
        updates: Field/value pairs to write (already validated/canonicalised).
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.
        not_found_label: Label used in the not-found message; defaults to
            *entity_name* capitalised.

    Returns:
        The updated instance; ``None`` on not-found or error.
    """

    async def _op() -> M | None:
        async with get_db_session(env, verbose) as session:
            results = await _rows_for_id(model_class, session, entity_id)
            if not results:
                label = not_found_label or entity_name.capitalize()
                print_error(f"{label} '{entity_id}' not found.")
                return None
            entity = results[0]
            await entity.update_fields(session, **updates)
            return entity

    return await _guarded(f"Failed to update {entity_name}", None, _op)
