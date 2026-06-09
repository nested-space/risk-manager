"""
Component salt CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import ComponentSalt
from ..schema.create import ComponentSaltCreate
from ..schema.update import ComponentSaltUpdate
from ..utils.console_formatting import print_error, print_success


async def create_component_salt(
    data: ComponentSaltCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ComponentSalt | None:
    """Create a salt formation record linking a component to a counterion.

    Args:
        data: Validated :class:`~..schema.create.ComponentSaltCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.ComponentSalt`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            salt = ComponentSalt(
                component_id=str(data.component_id),
                counterion_id=str(data.counterion_id),
                stoichiometry=data.stoichiometry,
                is_fully_defined=data.is_fully_defined,
            )
            session.add(salt)
            await session.commit()
            await session.refresh(salt)
            print_success("Created component salt record.")
            return salt
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create component salt: {exc}")
        return None


async def list_salts_for_component(
    component_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[ComponentSalt]:
    """Return all salt records for a component.

    Args:
        component_id: UUID of the component.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.ComponentSalt` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            return await ComponentSalt.get_where(
                session, ComponentSalt.component_id == str(component_id)
            )
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list component salts: {exc}")
        return []


async def update_component_salt(
    salt_id: UUID,
    data: ComponentSaltUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ComponentSalt | None:
    """Update a component salt record.

    Args:
        salt_id: UUID of the salt record to update.
        data: Validated :class:`~..schema.update.ComponentSaltUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.ComponentSalt`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ComponentSalt.get_where(session, ComponentSalt.id == str(salt_id))
            if not results:
                print_error(f"Component salt '{salt_id}' not found.")
                return None
            salt = results[0]
            await salt.update_fields(session, **data.model_dump(exclude_none=True))
            return salt
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update component salt: {exc}")
        return None


async def delete_component_salt(
    salt_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a component salt record by UUID.

    Args:
        salt_id: UUID of the salt record to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ComponentSalt.get_where(session, ComponentSalt.id == str(salt_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete component salt: {exc}")
        return False
