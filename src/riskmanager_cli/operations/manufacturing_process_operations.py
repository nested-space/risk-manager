"""
Manufacturing process (route) CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`;
only route-specific lookups live here.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import ManufacturingProcess
from ..schema.create import ManufacturingProcessCreate
from ..schema.update import ManufacturingProcessUpdate
from .base_operations import (
    db_operation,
    generic_create,
    generic_delete_by_id,
    generic_get_by_id,
    generic_update,
)


async def create_manufacturing_process(
    data: ManufacturingProcessCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcess | None:
    """Create a new manufacturing process (route + process combination); ``None`` on error."""
    process = ManufacturingProcess(
        project_id=str(data.project_id),
        route_number=data.route_number,
        process_number=data.process_number,
    )
    return await generic_create(
        process,
        "manufacturing process",
        env,
        verbose,
        success_message=(
            f"Created route {data.route_number}.{data.process_number} "
            f"for project '{data.project_id}'."
        ),
    )


async def get_process_by_id(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcess | None:
    """Retrieve a manufacturing process by UUID; ``None`` if not found."""
    return await generic_get_by_id(
        ManufacturingProcess, process_id, "manufacturing process", env, verbose
    )


@db_operation(default=None, error="Failed to get manufacturing process by route")
async def get_process_by_route(
    project_id: UUID,
    route_number: int,
    process_number: int,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcess | None:
    """Retrieve a manufacturing process by project + route + process numbers."""
    async with get_db_session(env, verbose) as session:
        from sqlalchemy import select  # pylint: disable=import-outside-toplevel

        result = await session.execute(
            select(ManufacturingProcess)
            # SQLModel instrumented __eq__ returns ColumnElement[bool] at runtime;
            # mypy infers bool due to SQLModel/SQLAlchemy stub gap — not a real error.
            .where(ManufacturingProcess.project_id == str(project_id))  # type: ignore[arg-type]
            .where(ManufacturingProcess.route_number == route_number)  # type: ignore[arg-type]
            .where(
                ManufacturingProcess.process_number  # type: ignore[arg-type]
                == process_number
            ),
        )
        rows = list(result.scalars().all())
        return rows[0] if rows else None


@db_operation(default=[], error="Failed to list manufacturing processes")
async def list_processes_for_project(
    project_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[ManufacturingProcess]:
    """Return all manufacturing processes for a project, ordered by route and process number."""
    async with get_db_session(env, verbose) as session:
        results = await ManufacturingProcess.get_where(
            session, ManufacturingProcess.project_id == str(project_id)
        )
        return sorted(results, key=lambda p: (p.route_number, p.process_number))


async def update_manufacturing_process(
    process_id: UUID,
    data: ManufacturingProcessUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcess | None:
    """Update route and/or process numbers on an existing process; ``None`` on not-found/error."""
    return await generic_update(
        ManufacturingProcess,
        process_id,
        "manufacturing process",
        data.model_dump(exclude_none=True),
        env=env,
        verbose=verbose,
    )


async def delete_manufacturing_process(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a manufacturing process by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(
        ManufacturingProcess, process_id, "manufacturing process", env, verbose
    )
