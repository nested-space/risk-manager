"""
Generic base operation helpers shared across all entity operations modules.

Provides four reusable async functions that handle the most common CRUD
patterns. Entity-specific modules call these instead of duplicating the
session/try/except boilerplate.

Why this exists:
    The 16 entity operations modules all follow identical patterns for
    get-by-id, existence checks, and stats retrieval. Extracting these
    reduces duplication while keeping each entity module focused on its
    own specialised logic.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import CRUDMixin
from ..utils.console_formatting import print_error

# Type alias: a callable that computes stats from a list of model instances.
StatsCalculator = Callable[[list[Any]], dict[str, Any]]


async def generic_get_by_id(
    model_class: type[CRUDMixin],
    entity_id: UUID,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Any | None:
    """Retrieve any entity by UUID primary key.

    Opens a new database session, queries by primary key, and returns the
    first matching record. Returns ``None`` on not-found or error.

    Args:
        model_class: The SQLModel table class to query.
        entity_id: UUID of the entity to retrieve.
        entity_name: Human-readable entity label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.

    Returns:
        The model instance if found; ``None`` otherwise.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await model_class.get_where(
                session,
                _id_column(model_class) == str(entity_id),
            )
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get {entity_name} by ID: {exc}")
        return None


async def generic_check_exists(
    model_class: type[CRUDMixin],
    entity_id: UUID,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Check whether an entity exists by UUID.

    Args:
        model_class: The SQLModel table class to query.
        entity_id: UUID to look up.
        entity_name: Human-readable entity label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.

    Returns:
        ``True`` if the entity exists; ``False`` otherwise.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await model_class.get_where(
                session,
                _id_column(model_class) == str(entity_id),
            )
            return len(results) > 0
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to check {entity_name} existence: {exc}")
        return False


async def generic_get_stats(
    model_class: type[CRUDMixin],
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
    stats_calculator: StatsCalculator | None = None,
) -> dict[str, Any]:
    """Return statistics for an entity type.

    Always includes a ``"total"`` key. Additional keys depend on
    *stats_calculator*.

    Args:
        model_class: The SQLModel table class to query.
        entity_name: Human-readable entity label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.
        stats_calculator: Optional callable that receives all records and
            returns a ``dict`` of additional statistics.

    Returns:
        A dict with at least ``{"total": N}``, or ``{"total": 0}`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            entities = await model_class.get_all(session)
            base: dict[str, Any] = {"total": len(entities)}
            if stats_calculator:
                base.update(stats_calculator(entities))
            return base
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get {entity_name} stats: {exc}")
        return {"total": 0}


async def generic_delete_by_id(
    model_class: type[CRUDMixin],
    entity_id: UUID,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete an entity by UUID primary key.

    Args:
        model_class: The SQLModel table class to query.
        entity_id: UUID of the entity to delete.
        entity_name: Human-readable entity label used in error messages.
        env: Database environment selector.
        verbose: If ``True``, prints the resolved database path.

    Returns:
        ``True`` if the entity was found and deleted; ``False`` otherwise.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await model_class.get_where(
                session,
                _id_column(model_class) == str(entity_id),
            )
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete {entity_name}: {exc}")
        return False


def _id_column(model_class: type[CRUDMixin]) -> Any:
    """Return the SQLAlchemy ``id`` column expression for *model_class*.

    Why this exists:
        SQLModel stores the primary key as a class attribute accessible via
        ``Model.id``. Using ``getattr`` here avoids a repeated attribute
        lookup pattern across all generic operations.

    Args:
        model_class: The SQLModel table class.

    Returns:
        The column expression for the ``id`` attribute.
    """
    return getattr(model_class, "id")


def run_async_in_session(
    session: AsyncSession,
    coro: Any,
) -> Any:
    """Placeholder for future session-sharing helpers.

    Not used directly — all operations open their own sessions via
    :func:`~..database.db_session.get_db_session`. Retained as a reference
    point for the session-per-operation design documented in
    ``AGENTS.md`` §5 (Async Patterns).

    Args:
        session: An open async session (unused in current implementation).
        coro: A coroutine object.

    Returns:
        The coroutine unchanged.
    """
    _ = session  # session-per-operation; not shared
    return coro
