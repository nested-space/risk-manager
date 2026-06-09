"""
Stage risk CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import StageRisk
from ..schema.create import StageRiskCreate
from ..schema.update import StageRiskUpdate
from ..utils.console_formatting import print_error, print_success


async def create_stage_risk(
    data: StageRiskCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageRisk | None:
    """Create a new stage risk record.

    Args:
        data: Validated :class:`~..schema.create.StageRiskCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.StageRisk`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            risk = StageRisk(
                stage_id=str(data.stage_id),
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
            print_success(f"Created stage risk '{risk.name}'.")
            return risk
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create stage risk: {exc}")
        return None


async def list_risks_for_stage(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[StageRisk]:
    """Return all risks for a stage, ordered by current level descending.

    Args:
        stage_id: UUID of the stage.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.StageRisk` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await StageRisk.get_where(session, StageRisk.stage_id == str(stage_id))
            return sorted(results, key=lambda r: r.current_level or 0, reverse=True)
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list stage risks: {exc}")
        return []


async def update_stage_risk(
    risk_id: UUID,
    data: StageRiskUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageRisk | None:
    """Update fields on an existing stage risk.

    Args:
        risk_id: UUID of the stage risk to update.
        data: Validated :class:`~..schema.update.StageRiskUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.StageRisk`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await StageRisk.get_where(session, StageRisk.id == str(risk_id))
            if not results:
                print_error(f"Stage risk '{risk_id}' not found.")
                return None
            risk = results[0]
            await risk.update_fields(session, **data.model_dump(exclude_none=True))
            return risk
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update stage risk: {exc}")
        return None


async def delete_stage_risk(
    risk_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Delete a stage risk by UUID.

    Args:
        risk_id: UUID of the stage risk to delete.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await StageRisk.get_where(session, StageRisk.id == str(risk_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete stage risk: {exc}")
        return False
