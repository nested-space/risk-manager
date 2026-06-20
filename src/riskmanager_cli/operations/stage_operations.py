"""
Stage CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`;
only stage-specific lookups live here.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Stage
from ..schema.create import StageCreate
from ..schema.update import StageUpdate
from .base_operations import (
    db_operation,
    generic_create,
    generic_delete_by_id,
    generic_get_by_id,
    generic_update,
)


async def create_stage(
    data: StageCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Stage | None:
    """Create a new stage within a manufacturing process; ``None`` on error."""
    stage = Stage(
        process_id=str(data.process_id),
        name=data.name,
        number=data.number,
    )
    return await generic_create(
        stage,
        "stage",
        env,
        verbose,
        success_message=f"Created stage '{data.name}' (#{data.number}).",
    )


async def get_stage_by_id(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Stage | None:
    """Retrieve a stage by UUID; ``None`` if not found."""
    return await generic_get_by_id(Stage, stage_id, "stage", env, verbose)


@db_operation(default=None, error="Failed to get stage by name")
async def get_stage_by_name(
    process_id: UUID,
    name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Stage | None:
    """Retrieve a stage by process ID and name; ``None`` if not found."""
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


@db_operation(default=[], error="Failed to list stages")
async def list_stages_for_process(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Stage]:
    """Return all stages for a manufacturing process, ordered by stage number."""
    async with get_db_session(env, verbose) as session:
        results = await Stage.get_where(session, Stage.process_id == str(process_id))
        return sorted(results, key=lambda s: s.number)


async def update_stage(
    stage_id: UUID,
    data: StageUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Stage | None:
    """Update fields on an existing stage; ``None`` on not-found or error."""
    return await generic_update(
        Stage, stage_id, "stage", data.model_dump(exclude_none=True), env=env, verbose=verbose
    )


async def delete_stage(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a stage by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(Stage, stage_id, "stage", env, verbose)
