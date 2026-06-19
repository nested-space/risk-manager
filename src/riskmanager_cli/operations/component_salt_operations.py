"""
Component salt CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``. The common
CRUD shapes delegate to the ``generic_*`` helpers in :mod:`.base_operations`.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import ComponentSalt
from ..schema.create import ComponentSaltCreate
from ..schema.update import ComponentSaltUpdate
from .base_operations import db_operation, generic_create, generic_delete_by_id, generic_update


@db_operation(default=None, error="Failed to create component salt")
async def create_component_salt(
    data: ComponentSaltCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ComponentSalt | None:
    """Create a salt formation record linking a component to a counterion; ``None`` on error."""
    salt = ComponentSalt(
        component_id=str(data.component_id),
        counterion_id=str(data.counterion_id),
        stoichiometry=data.stoichiometry,
        is_fully_defined=data.is_fully_defined,
    )
    return await generic_create(
        salt, "component salt", env, verbose, success_message="Created component salt record."
    )


@db_operation(default=[], error="Failed to list component salts")
async def list_salts_for_component(
    component_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[ComponentSalt]:
    """Return all salt records for a component."""
    async with get_db_session(env, verbose) as session:
        return await ComponentSalt.get_where(
            session, ComponentSalt.component_id == str(component_id)
        )


async def update_component_salt(
    salt_id: UUID,
    data: ComponentSaltUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ComponentSalt | None:
    """Update a component salt record; ``None`` on not-found or error."""
    return await generic_update(
        ComponentSalt,
        salt_id,
        "component salt",
        data.model_dump(exclude_none=True),
        env=env,
        verbose=verbose,
    )


async def delete_component_salt(
    salt_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a component salt record by UUID; ``False`` if not found or on error."""
    return await generic_delete_by_id(ComponentSalt, salt_id, "component salt", env, verbose)
