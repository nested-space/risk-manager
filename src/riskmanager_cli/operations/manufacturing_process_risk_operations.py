"""
Manufacturing process risk CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import ManufacturingProcessRisk
from ..schema.create import ManufacturingProcessRiskCreate
from ..schema.update import ManufacturingProcessRiskUpdate
from .base_operations import db_operation, generic_create, generic_delete_by_id, generic_update


@db_operation(default=None, error="Failed to create manufacturing process risk")
async def create_manufacturing_process_risk(
    data: ManufacturingProcessRiskCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcessRisk | None:
    """Create a new risk record for a manufacturing process; ``None`` on error."""
    risk = ManufacturingProcessRisk(
        manufacturing_process_id=str(data.manufacturing_process_id),
        risk_type=data.risk_type,
        name=data.name,
        description=data.description,
        current_level=data.current_level,
        proposed_mitigation=data.proposed_mitigation,
        mitigated_level=data.mitigated_level,
    )
    return await generic_create(
        risk,
        "manufacturing process risk",
        env,
        verbose,
        success_message=f"Created process risk '{data.name}'.",
    )


@db_operation(default=[], error="Failed to list manufacturing process risks")
async def list_risks_for_process(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[ManufacturingProcessRisk]:
    """Return all risks for a manufacturing process, ordered by current level descending."""
    async with get_db_session(env, verbose) as session:
        results = await ManufacturingProcessRisk.get_where(
            session,
            ManufacturingProcessRisk.manufacturing_process_id == str(process_id),
        )
        return sorted(results, key=lambda r: r.current_level or 0, reverse=True)


async def update_manufacturing_process_risk(
    risk_id: UUID,
    data: ManufacturingProcessRiskUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcessRisk | None:
    """Update fields on an existing manufacturing process risk; ``None`` on not-found or error."""
    return await generic_update(
        ManufacturingProcessRisk,
        risk_id,
        "manufacturing process risk",
        data.model_dump(exclude_none=True),
        env=env,
        verbose=verbose,
    )


async def delete_manufacturing_process_risk(
    risk_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a manufacturing process risk by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(
        ManufacturingProcessRisk, risk_id, "manufacturing process risk", env, verbose
    )
