"""
Manufacturing process (route) CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import ManufacturingProcess
from ..schema.create import ManufacturingProcessCreate
from ..schema.update import ManufacturingProcessUpdate
from ..utils.console_formatting import print_error, print_success


async def create_manufacturing_process(
    data: ManufacturingProcessCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcess | None:
    """Create a new manufacturing process (route + process combination).

    Args:
        data: Validated :class:`~..schema.create.ManufacturingProcessCreate`.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.ManufacturingProcess`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            process = ManufacturingProcess(
                project_id=str(data.project_id),
                route_number=data.route_number,
                process_number=data.process_number,
            )
            session.add(process)
            await session.commit()
            await session.refresh(process)
            print_success(
                f"Created route {data.route_number}.{data.process_number} "
                f"for project '{data.project_id}'."
            )
            return process
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create manufacturing process: {exc}")
        return None


async def get_process_by_id(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcess | None:
    """Retrieve a manufacturing process by UUID.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.ManufacturingProcess`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ManufacturingProcess.get_where(
                session, ManufacturingProcess.id == str(process_id)
            )
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get manufacturing process by ID: {exc}")
        return None


async def get_process_by_route(
    project_id: UUID,
    route_number: int,
    process_number: int,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcess | None:
    """Retrieve a manufacturing process by project + route + process numbers.

    Args:
        project_id: UUID of the parent project.
        route_number: Route identifier within the project.
        process_number: Process identifier within the route.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.ManufacturingProcess`; ``None`` if not found.
    """
    try:
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
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get manufacturing process by route: {exc}")
        return None


async def list_processes_for_project(
    project_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[ManufacturingProcess]:
    """Return all manufacturing processes for a project, ordered by route and process number.

    Args:
        project_id: UUID of the parent project.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        Ordered list of :class:`~..model.tables.ManufacturingProcess` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ManufacturingProcess.get_where(
                session, ManufacturingProcess.project_id == str(project_id)
            )
            return sorted(results, key=lambda p: (p.route_number, p.process_number))
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list manufacturing processes: {exc}")
        return []


async def update_manufacturing_process(
    process_id: UUID,
    data: ManufacturingProcessUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcess | None:
    """Update route and/or process numbers on an existing manufacturing process.

    Args:
        process_id: UUID of the manufacturing process to update.
        data: Validated :class:`~..schema.update.ManufacturingProcessUpdate`.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.ManufacturingProcess`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ManufacturingProcess.get_where(
                session, ManufacturingProcess.id == str(process_id)
            )
            if not results:
                print_error(f"Manufacturing process '{process_id}' not found.")
                return None
            process = results[0]
            await process.update_fields(session, **data.model_dump(exclude_none=True))
            return process
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update manufacturing process: {exc}")
        return None


async def delete_manufacturing_process(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a manufacturing process by UUID.

    Args:
        process_id: UUID of the manufacturing process to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ManufacturingProcess.get_where(
                session, ManufacturingProcess.id == str(process_id)
            )
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete manufacturing process: {exc}")
        return False
