"""
Project CRUD and search operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Project
from ..schema.create import ProjectCreate
from ..schema.update import ProjectUpdate
from ..utils.console_formatting import print_error, print_success


async def create_project(
    data: ProjectCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Project | None:
    """Create a new project.

    Args:
        data: Validated :class:`~..schema.create.ProjectCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.Project`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            project = Project(
                name=data.name,
                therapy_area=data.therapy_area,
                material_id=str(data.material_id),
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            print_success(f"Created project '{project.name}'.")
            return project
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create project: {exc}")
        return None


async def get_project_by_id(
    project_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Project | None:
    """Retrieve a project by UUID.

    Args:
        project_id: UUID of the project.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Project`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Project.get_where(session, Project.id == str(project_id))
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get project by ID: {exc}")
        return None


async def get_project_by_name(
    name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Project | None:
    """Retrieve a project by exact name.

    Args:
        name: Exact project name string.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The first matching :class:`~..model.tables.Project`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Project.get_where(session, Project.name == name)
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get project by name: {exc}")
        return None


async def search_projects(
    query: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Project]:
    """Search projects by partial name match (case-insensitive).

    Args:
        query: Partial name string to search for.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of matching :class:`~..model.tables.Project` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            from sqlalchemy import func  # pylint: disable=import-outside-toplevel

            results = await Project.get_where(
                session,
                func.lower(Project.name).contains(query.lower()),
            )
            return sorted(results, key=lambda p: p.name)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to search projects: {exc}")
        return []


async def list_projects(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Project]:
    """Return all projects ordered by name.

    Args:
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.Project` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Project.get_all(session)
            return sorted(results, key=lambda p: p.name)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list projects: {exc}")
        return []


async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Project | None:
    """Update fields on an existing project.

    Args:
        project_id: UUID of the project to update.
        data: Validated :class:`~..schema.update.ProjectUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.Project`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Project.get_where(session, Project.id == str(project_id))
            if not results:
                print_error(f"Project '{project_id}' not found.")
                return None
            project = results[0]
            updates = data.model_dump(exclude_none=True)
            if "material_id" in updates:
                updates["material_id"] = str(updates["material_id"])
            await project.update_fields(session, **updates)
            return project
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update project: {exc}")
        return None


async def delete_project(
    project_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a project by UUID.

    Args:
        project_id: UUID of the project to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Project.get_where(session, Project.id == str(project_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete project: {exc}")
        return False
