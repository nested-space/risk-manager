"""
Manufacturing process risk CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import ManufacturingProcessRisk
from ..schema.create import ManufacturingProcessRiskCreate
from ..schema.update import ManufacturingProcessRiskUpdate
from ..utils.console_formatting import print_error, print_success


async def create_manufacturing_process_risk(
    data: ManufacturingProcessRiskCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcessRisk | None:
    """Create a new risk record for a manufacturing process.

    Args:
        data: Validated :class:`~..schema.create.ManufacturingProcessRiskCreate`.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.ManufacturingProcessRisk`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            risk = ManufacturingProcessRisk(
                manufacturing_process_id=str(data.manufacturing_process_id),
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
            print_success(f"Created process risk '{risk.name}'.")
            return risk
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create manufacturing process risk: {exc}")
        return None


async def list_risks_for_process(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[ManufacturingProcessRisk]:
    """Return all risks for a manufacturing process, ordered by current level descending.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.ManufacturingProcessRisk` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ManufacturingProcessRisk.get_where(
                session,
                ManufacturingProcessRisk.manufacturing_process_id == str(process_id),
            )
            return sorted(results, key=lambda r: r.current_level or 0, reverse=True)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list manufacturing process risks: {exc}")
        return []


async def update_manufacturing_process_risk(
    risk_id: UUID,
    data: ManufacturingProcessRiskUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> ManufacturingProcessRisk | None:
    """Update fields on an existing manufacturing process risk.

    Args:
        risk_id: UUID of the risk to update.
        data: Validated :class:`~..schema.update.ManufacturingProcessRiskUpdate`.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.ManufacturingProcessRisk`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ManufacturingProcessRisk.get_where(
                session, ManufacturingProcessRisk.id == str(risk_id)
            )
            if not results:
                print_error(f"Manufacturing process risk '{risk_id}' not found.")
                return None
            risk = results[0]
            await risk.update_fields(session, **data.model_dump(exclude_none=True))
            return risk
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update manufacturing process risk: {exc}")
        return None


async def delete_manufacturing_process_risk(
    risk_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a manufacturing process risk by UUID.

    Args:
        risk_id: UUID of the risk to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await ManufacturingProcessRisk.get_where(
                session, ManufacturingProcessRisk.id == str(risk_id)
            )
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete manufacturing process risk: {exc}")
        return False
