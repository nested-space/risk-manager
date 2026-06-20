"""
Project CRUD and search operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`;
only project-specific logic (partial-name search) lives here.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Project
from ..schema.create import ProjectCreate
from ..schema.update import ProjectUpdate
from .base_operations import (
    db_operation,
    generic_create,
    generic_delete_by_id,
    generic_get_by_id,
    generic_list,
    generic_update,
)


async def create_project(
    data: ProjectCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Project | None:
    """Create a new project; ``None`` on error."""
    project = Project(
        name=data.name,
        therapy_area=data.therapy_area,
        material_id=str(data.material_id),
    )
    return await generic_create(
        project, "project", env, verbose, success_message=f"Created project '{data.name}'."
    )


async def get_project_by_id(
    project_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Project | None:
    """Retrieve a project by UUID; ``None`` if not found."""
    return await generic_get_by_id(Project, project_id, "project", env, verbose)


@db_operation(default=None, error="Failed to get project by name")
async def get_project_by_name(
    name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Project | None:
    """Retrieve a project by exact name; ``None`` if not found."""
    async with get_db_session(env, verbose) as session:
        results = await Project.get_where(session, Project.name == name)
        return results[0] if results else None


@db_operation(default=[], error="Failed to search projects")
async def search_projects(
    query: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Project]:
    """Search projects by partial name match (case-insensitive)."""
    async with get_db_session(env, verbose) as session:
        from sqlalchemy import func  # pylint: disable=import-outside-toplevel

        results = await Project.get_where(
            session,
            func.lower(Project.name).contains(query.lower()),
        )
        return sorted(results, key=lambda p: p.name)


async def list_projects(
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Project]:
    """Return all projects ordered by name."""
    return await generic_list(Project, "projects", env, verbose, sort_key=lambda p: p.name)


async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Project | None:
    """Update fields on an existing project; ``None`` on not-found or error."""
    updates = data.model_dump(exclude_none=True)
    if "material_id" in updates:
        updates["material_id"] = str(updates["material_id"])
    return await generic_update(Project, project_id, "project", updates, env=env, verbose=verbose)


async def delete_project(
    project_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a project by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(Project, project_id, "project", env, verbose)
