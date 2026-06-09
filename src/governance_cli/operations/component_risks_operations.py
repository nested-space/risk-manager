"""
Component risk CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import ComponentRisk
from ..schema.create import ComponentRiskCreate
from ..schema.update import ComponentRiskUpdate
from ..utils.console_formatting import print_error, print_success


async def create_component_risk(
    data: ComponentRiskCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ComponentRisk | None:
    """Create a new component risk record.

    Args:
        data: Validated :class:`~..schema.create.ComponentRiskCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.ComponentRisk`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            risk = ComponentRisk(
                component_id=str(data.component_id),
                risk_type=data.risk_type,
                name=data.name,
                description=data.description,
                current_level=data.current_level,
                proposed_mitigation=data.proposed_mitigation,
                mitigated_level=data.mitigated_level,
            )
            session.add(risk)
            await session.commit()
            await session.refresh(risk)
            print_success(f"Created component risk '{risk.name}'.")
            return risk
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create component risk: {exc}")
        return None


async def list_risks_for_component(
    component_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[ComponentRisk]:
    """Return all risks for a component, ordered by current level descending.

    Args:
        component_id: UUID of the component.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.ComponentRisk` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ComponentRisk.get_where(
                session, ComponentRisk.component_id == str(component_id)
            )
            return sorted(results, key=lambda r: r.current_level or 0, reverse=True)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list component risks: {exc}")
        return []


async def update_component_risk(
    risk_id: UUID,
    data: ComponentRiskUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ComponentRisk | None:
    """Update fields on an existing component risk.

    Args:
        risk_id: UUID of the risk record to update.
        data: Validated :class:`~..schema.update.ComponentRiskUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.ComponentRisk`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ComponentRisk.get_where(session, ComponentRisk.id == str(risk_id))
            if not results:
                print_error(f"Component risk '{risk_id}' not found.")
                return None
            risk = results[0]
            await risk.update_fields(session, **data.model_dump(exclude_none=True))
            return risk
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update component risk: {exc}")
        return None


async def delete_component_risk(
    risk_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a component risk by UUID.

    Args:
        risk_id: UUID of the component risk to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ComponentRisk.get_where(session, ComponentRisk.id == str(risk_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete component risk: {exc}")
        return False
