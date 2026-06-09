"""
Stage–NCRM junction CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import StageNcrm
from ..schema.create import StageNcrmCreate
from ..schema.update import StageNcrmUpdate
from ..utils.console_formatting import print_error, print_success


async def create_stage_ncrm(
    data: StageNcrmCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageNcrm | None:
    """Link an NCRM library entry to a stage with its role.

    Args:
        data: Validated :class:`~..schema.create.StageNcrmCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.StageNcrm`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            link = StageNcrm(
                ncrm_id=str(data.ncrm_id),
                stage_id=str(data.stage_id),
                role=data.role,
            )
            session.add(link)
            await session.commit()
            await session.refresh(link)
            print_success(
                f"Linked NCRM '{data.ncrm_id}' to stage '{data.stage_id}' as '{data.role.value}'."
            )
            return link
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create stage-NCRM link: {exc}")
        return None


async def list_ncrms_for_stage(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[StageNcrm]:
    """Return all NCRM links for a stage.

    Args:
        stage_id: UUID of the stage.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.StageNcrm` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            return await StageNcrm.get_where(session, StageNcrm.stage_id == str(stage_id))
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list stage NCRMs: {exc}")
        return []


async def update_stage_ncrm(
    link_id: UUID,
    data: StageNcrmUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageNcrm | None:
    """Update the role on an existing stage-NCRM link.

    Args:
        link_id: UUID of the stage-NCRM link to update.
        data: Validated :class:`~..schema.update.StageNcrmUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.StageNcrm`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await StageNcrm.get_where(session, StageNcrm.id == str(link_id))
            if not results:
                print_error(f"Stage-NCRM link '{link_id}' not found.")
                return None
            link = results[0]
            await link.update_fields(session, **data.model_dump(exclude_none=True))
            return link
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update stage-NCRM link: {exc}")
        return None


async def delete_stage_ncrm(
    link_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Remove a stage-NCRM link by UUID.

    Args:
        link_id: UUID of the stage-NCRM link to remove.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await StageNcrm.get_where(session, StageNcrm.id == str(link_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete stage-NCRM link: {exc}")
        return False
