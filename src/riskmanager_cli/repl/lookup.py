"""Entity lookups shared across screens and the dispatcher.

Stateless async helpers that resolve domain entities from the navigation context
or from raw identifiers. They take the active :class:`ContextManager` and/or
:class:`Environment` explicitly so any screen or the dispatcher can call them
without reaching into each other's internals.
"""

from __future__ import annotations

from uuid import UUID

from ..config.settings import Environment
from ..model.tables import Component, ManufacturingProcess, Project, Stage
from ..operations.component_operations import (
    get_component_by_id,
    list_components_for_process,
)
from ..operations.manufacturing_process_operations import (
    get_process_by_id,
    get_process_by_route,
)
from ..operations.material_operations import get_material_by_id
from ..operations.project_operations import get_project_by_id
from ..operations.stage_operations import get_stage_by_name, list_stages_for_process
from .context import ContextManager


async def project_from_id(env: Environment, project_id: str | None) -> Project | None:
    """Return the project with *project_id*, or ``None`` when unset/not found."""
    if project_id is None:
        return None
    return await get_project_by_id(UUID(project_id), env)


async def process_from_id(env: Environment, process_id: str | None) -> ManufacturingProcess | None:
    """Return the process with *process_id*, or ``None`` when unset/not found."""
    if process_id is None:
        return None
    return await get_process_by_id(UUID(process_id), env)


async def process_from_route_label(
    env: Environment, project_id: str, route_label: str
) -> ManufacturingProcess | None:
    """Resolve a ``route.process`` label within a project to its process."""
    try:
        route_number_text, process_number_text = route_label.split(".", maxsplit=1)
        return await get_process_by_route(
            UUID(project_id),
            int(route_number_text),
            int(process_number_text),
            env,
        )
    except ValueError:
        return None


async def current_project(ctx: ContextManager, env: Environment) -> Project | None:
    """Return the project referenced by the current navigation frame."""
    return await project_from_id(env, ctx.current.project_id)


async def current_process(ctx: ContextManager, env: Environment) -> ManufacturingProcess | None:
    """Return the process referenced by the current navigation frame."""
    return await process_from_id(env, ctx.current.process_id)


async def current_stage(ctx: ContextManager, env: Environment) -> Stage | None:
    """Return the stage referenced by the current navigation frame, if any."""
    stage_id = ctx.current.stage_id
    if stage_id is None:
        return None
    process = await current_process(ctx, env)
    if process is None:
        return None
    for stage in await list_stages_for_process(UUID(str(process.id)), env):
        if str(stage.id) == stage_id:
            return stage
    return None


async def current_component(ctx: ContextManager, env: Environment) -> Component | None:
    """Return the component referenced by the current navigation frame, if any."""
    component_id = ctx.current.component_id
    if component_id is None:
        return None
    return await get_component_by_id(UUID(component_id), env)


async def find_stage(env: Environment, process: ManufacturingProcess, name: str) -> Stage | None:
    """Find a stage of *process* by exact name, then by case-insensitive substring."""
    lowered = name.lower()
    exact = await get_stage_by_name(UUID(str(process.id)), name, env)
    if exact is not None:
        return exact
    for stage in await list_stages_for_process(UUID(str(process.id)), env):
        if lowered in stage.name.lower():
            return stage
    return None


async def find_component(
    env: Environment, process: ManufacturingProcess, name: str
) -> Component | None:
    """Find a component of *process* by material name or control-strategy role."""
    lowered = name.lower()
    for component in await list_components_for_process(UUID(str(process.id)), env):
        material = await get_material_by_id(UUID(str(component.material_id)), env)
        material_name = material.name if material else ""
        if (
            lowered in material_name.lower()
            or lowered in (component.control_strategy_role or "").lower()
        ):
            return component
    return None
