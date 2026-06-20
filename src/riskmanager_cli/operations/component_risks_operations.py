"""
Component risk CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import ComponentRisk
from ..schema.create import ComponentRiskCreate
from ..schema.update import ComponentRiskUpdate
from .base_operations import db_operation, generic_create, generic_delete_by_id, generic_update


@db_operation(default=None, error="Failed to create component risk")
async def create_component_risk(
    data: ComponentRiskCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ComponentRisk | None:
    """Create a new component risk record; ``None`` on error."""
    risk = ComponentRisk(
        component_id=str(data.component_id),
        risk_type=data.risk_type,
        name=data.name,
        description=data.description,
        current_level=data.current_level,
        proposed_mitigation=data.proposed_mitigation,
        mitigated_level=data.mitigated_level,
    )
    return await generic_create(
        risk,
        "component risk",
        env,
        verbose,
        success_message=f"Created component risk '{data.name}'.",
    )


@db_operation(default=[], error="Failed to list component risks")
async def list_risks_for_component(
    component_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[ComponentRisk]:
    """Return all risks for a component, ordered by current level descending."""
    async with get_db_session(env, verbose) as session:
        results = await ComponentRisk.get_where(
            session, ComponentRisk.component_id == str(component_id)
        )
        return sorted(results, key=lambda r: r.current_level or 0, reverse=True)


async def update_component_risk(
    risk_id: UUID,
    data: ComponentRiskUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ComponentRisk | None:
    """Update fields on an existing component risk; ``None`` on not-found or error."""
    return await generic_update(
        ComponentRisk,
        risk_id,
        "component risk",
        data.model_dump(exclude_none=True),
        env=env,
        verbose=verbose,
    )


async def delete_component_risk(
    risk_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a component risk by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(ComponentRisk, risk_id, "component risk", env, verbose)
