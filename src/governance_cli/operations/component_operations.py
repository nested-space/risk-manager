"""
Component CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import Component
from ..schema.create import ComponentCreate
from ..schema.update import ComponentUpdate
from ..utils.console_formatting import print_error, print_success


async def create_component(
    data: ComponentCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Component | None:
    """Create a new component record.

    Args:
        data: Validated :class:`~..schema.create.ComponentCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.Component`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            component = Component(
                process_id=str(data.process_id),
                material_id=str(data.material_id),
                control_strategy_role=data.control_strategy_role,
                is_isolated=data.is_isolated,
            )
            session.add(component)
            await session.commit()
            await session.refresh(component)
            print_success(f"Created component (material ID: {data.material_id}).")
            return component
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create component: {exc}")
        return None


async def get_component_by_id(
    component_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Component | None:
    """Retrieve a component by UUID.

    Args:
        component_id: UUID of the component.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The :class:`~..model.tables.Component`; ``None`` if not found.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Component.get_where(session, Component.id == str(component_id))
            return results[0] if results else None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to get component by ID: {exc}")
        return None


async def list_components_for_process(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[Component]:
    """Return all components for a manufacturing process.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.Component` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            return await Component.get_where(session, Component.process_id == str(process_id))
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list components: {exc}")
        return []


async def update_component(
    component_id: UUID,
    data: ComponentUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Component | None:
    """Update fields on an existing component.

    Args:
        component_id: UUID of the component to update.
        data: Validated :class:`~..schema.update.ComponentUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.Component`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Component.get_where(session, Component.id == str(component_id))
            if not results:
                print_error(f"Component '{component_id}' not found.")
                return None
            component = results[0]
            await component.update_fields(session, **data.model_dump(exclude_none=True))
            return component
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update component: {exc}")
        return None


async def delete_component(
    component_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a component by UUID.

    Args:
        component_id: UUID of the component to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await Component.get_where(session, Component.id == str(component_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete component: {exc}")
        return False
