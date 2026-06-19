"""
Stage–NCRM junction CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import StageNcrm
from ..schema.create import StageNcrmCreate
from ..schema.update import StageNcrmUpdate
from .base_operations import db_operation, generic_create, generic_delete_by_id, generic_update


@db_operation(default=None, error="Failed to create stage-NCRM link")
async def create_stage_ncrm(
    data: StageNcrmCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageNcrm | None:
    """Link an NCRM library entry to a stage with its role; ``None`` on error."""
    link = StageNcrm(
        ncrm_id=str(data.ncrm_id),
        stage_id=str(data.stage_id),
        role=data.role,
    )
    return await generic_create(
        link,
        "stage-NCRM link",
        env,
        verbose,
        success_message=(
            f"Linked NCRM '{data.ncrm_id}' to stage '{data.stage_id}' as '{data.role.value}'."
        ),
    )


@db_operation(default=[], error="Failed to list stage NCRMs")
async def list_ncrms_for_stage(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[StageNcrm]:
    """Return all NCRM links for a stage."""
    async with get_db_session(env, verbose) as session:
        return await StageNcrm.get_where(session, StageNcrm.stage_id == str(stage_id))


async def update_stage_ncrm(
    link_id: UUID,
    data: StageNcrmUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageNcrm | None:
    """Update the role on an existing stage-NCRM link; ``None`` on not-found or error."""
    return await generic_update(
        StageNcrm,
        link_id,
        "stage-NCRM link",
        data.model_dump(exclude_none=True),
        env=env,
        verbose=verbose,
        not_found_label="Stage-NCRM link",
    )


async def delete_stage_ncrm(
    link_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Remove a stage-NCRM link by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(StageNcrm, link_id, "stage-NCRM link", env, verbose)
