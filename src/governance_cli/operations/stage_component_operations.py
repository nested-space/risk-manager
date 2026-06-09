"""
Stage–component junction CRUD operations.

All functions are ``async def`` and open their own sessions. On error they
log via ``print_error`` and return ``None`` / ``[]`` / ``False``.
"""

from uuid import UUID

from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..model.tables import StageComponent
from ..schema.create import StageComponentCreate
from ..schema.update import StageComponentUpdate
from ..utils.console_formatting import print_error, print_success


async def create_stage_component(
    data: StageComponentCreate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageComponent | None:
    """Link a component to a stage.

    Args:
        data: Validated :class:`~..schema.create.StageComponentCreate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The created :class:`~..model.tables.StageComponent`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            link = StageComponent(
                stage_id=str(data.stage_id),
                component_id=str(data.component_id),
                component_type=data.component_type,
            )
            session.add(link)
            await session.commit()
            await session.refresh(link)
            print_success(
                f"Linked component '{data.component_id}' to stage '{data.stage_id}' "
                f"as '{data.component_type}'."
            )
            return link
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to create stage-component link: {exc}")
        return None


async def list_stage_components(
    stage_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[StageComponent]:
    """Return all component links for a stage.

    Args:
        stage_id: UUID of the stage.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        List of :class:`~..model.tables.StageComponent` instances.
    """
    try:
        async with get_db_session(env, verbose) as session:
            return await StageComponent.get_where(session, StageComponent.stage_id == str(stage_id))
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to list stage components: {exc}")
        return []


async def update_stage_component(
    link_id: UUID,
    data: StageComponentUpdate,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> StageComponent | None:
    """Update the component type on a stage-component link.

    Args:
        link_id: UUID of the stage-component link.
        data: Validated :class:`~..schema.update.StageComponentUpdate` payload.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        The updated :class:`~..model.tables.StageComponent`; ``None`` on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await StageComponent.get_where(session, StageComponent.id == str(link_id))
            if not results:
                print_error(f"Stage-component link '{link_id}' not found.")
                return None
            link = results[0]
            await link.update_fields(session, **data.model_dump(exclude_none=True))
            return link
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to update stage-component link: {exc}")
        return None


async def delete_stage_component(
    link_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Remove a stage-component link by UUID.

    Args:
        link_id: UUID of the stage-component link.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        ``True`` if deleted; ``False`` if not found or on error.
    """
    try:
        async with get_db_session(env, verbose) as session:
            results = await StageComponent.get_where(session, StageComponent.id == str(link_id))
            if not results:
                return False
            await session.delete(results[0])
            await session.commit()
            return True
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"Failed to delete stage-component link: {exc}")
        return False
