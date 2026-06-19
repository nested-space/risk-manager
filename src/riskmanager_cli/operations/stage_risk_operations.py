"""
Stage risk CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import StageRisk
from ..schema.create import StageRiskCreate
from ..schema.update import StageRiskUpdate
from .base_operations import db_operation, generic_create, generic_delete_by_id, generic_update


@db_operation(default=None, error="Failed to create stage risk")
async def create_stage_risk(
    data: StageRiskCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageRisk | None:
    """Create a new stage risk record; ``None`` on error."""
    risk = StageRisk(
        stage_id=str(data.stage_id),
        risk_type=data.risk_type,
        name=data.name,
        description=data.description,
        current_level=data.current_level,
        proposed_mitigation=data.proposed_mitigation,
        mitigated_level=data.mitigated_level,
    )
    return await generic_create(
        risk, "stage risk", env, verbose, success_message=f"Created stage risk '{data.name}'."
    )


@db_operation(default=[], error="Failed to list stage risks")
async def list_risks_for_stage(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[StageRisk]:
    """Return all risks for a stage, ordered by current level descending."""
    async with get_db_session(env, verbose) as session:
        results = await StageRisk.get_where(session, StageRisk.stage_id == str(stage_id))
        return sorted(results, key=lambda r: r.current_level or 0, reverse=True)


async def update_stage_risk(
    risk_id: UUID,
    data: StageRiskUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageRisk | None:
    """Update fields on an existing stage risk; ``None`` on not-found or error."""
    return await generic_update(
        StageRisk,
        risk_id,
        "stage risk",
        data.model_dump(exclude_none=True),
        env=env,
        verbose=verbose,
    )


async def delete_stage_risk(
    risk_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a stage risk by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(StageRisk, risk_id, "stage risk", env, verbose)
