"""Builders for the stage/component typeahead-picker item lists.

Stateless helpers that turn a process's stages and components into
:class:`ListItem` lists for the modal picker, shared by the route and stage
screens. They take the active :class:`Environment` explicitly.
"""

from __future__ import annotations

from uuid import UUID

from ..config.settings import Environment
from ..model.tables import ManufacturingProcess, Stage
from ..operations.component_operations import (
    component_display_name,
    list_components_for_process,
)
from ..operations.stage_component_operations import list_stage_components
from ..operations.stage_operations import list_stages_for_process
from ..repl_engine.list_navigator import ListItem


async def stage_items(env: Environment, process: ManufacturingProcess) -> list[ListItem]:
    """Build picker items for every stage in *process*, labelled by name."""
    stages = await list_stages_for_process(UUID(str(process.id)), env)
    return [ListItem(label=stage.name, item_id=str(stage.id)) for stage in stages]


async def component_assignment_map(
    env: Environment, process: ManufacturingProcess
) -> dict[str, list[tuple[int, str]]]:
    """Map each component id to its ``(stage_number, component_type)`` links."""
    assignments: dict[str, list[tuple[int, str]]] = {}
    for stage in await list_stages_for_process(UUID(str(process.id)), env):
        for link in await list_stage_components(UUID(str(stage.id)), env):
            assignments.setdefault(str(link.component_id), []).append(
                (stage.number, link.component_type)
            )
    return assignments


async def process_component_items(
    env: Environment, process: ManufacturingProcess
) -> list[ListItem]:
    """Build picker items for every component in *process*, labelled by salt-form name.

    Each item's subtitle summarises the component's current stage assignments
    (``Stage {n} {role}``, comma-separated) so that several components sharing a
    material — e.g. a reactant reused across stages — stay distinguishable.
    Components with no assignments read ``unassigned``.
    """
    components = await list_components_for_process(UUID(str(process.id)), env)
    assignments = await component_assignment_map(env, process)
    items: list[ListItem] = []
    for component in components:
        label = await component_display_name(component, env)
        if component.control_strategy_role:
            label = f"{label} ({component.control_strategy_role})"
        entries = sorted(assignments.get(str(component.id), []))
        subtitle = (
            ", ".join(f"Stage {number} {role}" for number, role in entries)
            if entries
            else "unassigned"
        )
        items.append(ListItem(label=label, subtitle=subtitle, item_id=str(component.id)))
    return items


async def stage_component_link_id(env: Environment, stage: Stage, component_id: str) -> UUID | None:
    """Resolve the stage-component link id for a component row's component id."""
    for link in await list_stage_components(UUID(str(stage.id)), env):
        if str(link.component_id) == component_id:
            return UUID(str(link.id))
    return None
