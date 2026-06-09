"""
Stage CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Stage
from ..schema.create import StageCreate
from ..schema.update import StageUpdate
from ..utils.console_formatting import print_error, print_success


async def create_stage(
    data: StageCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Stage | None:
    """Create a new stage within a manufacturing process.

    Args:
        data: Validated :class:`~..schema.create.StageCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.Stage`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            stage = Stage(
                process_id=str(data.process_id),
                name=data.name,
                number=data.number,
            )
            session.add(stage)
            await session.commit()
            await session.refresh(stage)
            print_success(f"Created stage '{stage.name}' (#{stage.number}).")
            return stage
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create stage: {exc}")
        return None


async def get_stage_by_id(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Stage | None:
    """Retrieve a stage by UUID.

    Args:
        stage_id: UUID of the stage.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Stage`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Stage.get_where(session, Stage.id == str(stage_id))
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get stage by ID: {exc}")
        return None


async def get_stage_by_name(
    process_id: UUID,
    name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Stage | None:
    """Retrieve a stage by process ID and name.

    Args:
        process_id: UUID of the parent manufacturing process.
        name: Exact stage name.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Stage`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            from sqlalchemy import select  # pylint: disable=import-outside-toplevel

            result = await session.execute(
                select(Stage)
                # SQLModel instrumented __eq__ returns ColumnElement[bool] at runtime;
                # mypy infers bool due to SQLModel/SQLAlchemy stub gap — not a real error.
                .where(Stage.process_id == str(process_id))  # type: ignore[arg-type]
                .where(Stage.name == name),  # type: ignore[arg-type]
            )
            rows = list(result.scalars().all())
            return rows[0] if rows else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get stage by name: {exc}")
        return None


async def list_stages_for_process(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Stage]:
    """Return all stages for a manufacturing process, ordered by stage number.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        Ordered list of :class:`~..model.tables.Stage` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Stage.get_where(session, Stage.process_id == str(process_id))
            return sorted(results, key=lambda s: s.number)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list stages: {exc}")
        return []


async def update_stage(
    stage_id: UUID,
    data: StageUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Stage | None:
    """Update fields on an existing stage.

    Args:
        stage_id: UUID of the stage to update.
        data: Validated :class:`~..schema.update.StageUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.Stage`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Stage.get_where(session, Stage.id == str(stage_id))
            if not results:
                print_error(f"Stage '{stage_id}' not found.")
                return None
            stage = results[0]
            await stage.update_fields(session, **data.model_dump(exclude_none=True))
            return stage
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update stage: {exc}")
        return None


async def delete_stage(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a stage by UUID.

    Args:
        stage_id: UUID of the stage to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Stage.get_where(session, Stage.id == str(stage_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete stage: {exc}")
        return False
