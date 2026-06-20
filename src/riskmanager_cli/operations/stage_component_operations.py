"""
Stage–component junction CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import StageComponent
from ..schema.create import StageComponentCreate
from ..schema.update import StageComponentUpdate
from .base_operations import db_operation, generic_create, generic_delete_by_id, generic_update


@db_operation(default=None, error="Failed to create stage-component link")
async def create_stage_component(
    data: StageComponentCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageComponent | None:
    """Link a component to a stage; ``None`` on error."""
    link = StageComponent(
        stage_id=str(data.stage_id),
        component_id=str(data.component_id),
        component_type=data.component_type,
    )
    return await generic_create(
        link,
        "stage-component link",
        env,
        verbose,
        success_message=(
            f"Linked component '{data.component_id}' to stage '{data.stage_id}' "
            f"as '{data.component_type}'."
        ),
    )


@db_operation(default=[], error="Failed to list stage components")
async def list_stage_components(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[StageComponent]:
    """Return all component links for a stage."""
    async with get_db_session(env, verbose) as session:
        return await StageComponent.get_where(session, StageComponent.stage_id == str(stage_id))


async def update_stage_component(
    link_id: UUID,
    data: StageComponentUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageComponent | None:
    """Update the component type on a stage-component link; ``None`` on not-found or error."""
    return await generic_update(
        StageComponent,
        link_id,
        "stage-component link",
        data.model_dump(exclude_none=True),
        env=env,
        verbose=verbose,
    )


async def delete_stage_component(
    link_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Remove a stage-component link by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(StageComponent, link_id, "stage-component link", env, verbose)
