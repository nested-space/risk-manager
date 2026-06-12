"""
Visualization operations for manufacturing route ASCII layout.

Bridges the operations layer (database queries) with the layout engines
(``utils/component_graph_layout.py``) to produce printable route diagrams.
Used by the route view renderer (``repl/renderers/route_renderer.py``).

Why this exists:
    The layout engines are pure utilities that know nothing about the database.
    This module fetches the required data and converts it into the
    ``StageInput``/``ComponentInput`` structures the layout engines consume.
"""

from uuid import UUID

from ..config.settings import Environment
from ..utils.component_graph_layout import (
    ComponentInput,
    StageComponentInput,
    StageInput,
)
from .component_operations import component_display_name, list_components_for_process
from .stage_component_operations import list_stage_components
from .stage_operations import list_stages_for_process
from .stage_risk_operations import list_risks_for_stage


async def get_graph_inputs(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> tuple[list[StageInput], list[ComponentInput]] | None:
    """Fetch the data needed to lay out the process as a component DAG.

    Loads the process's stages, their component links, and the components
    themselves, returning the pure ``StageInput``/``ComponentInput`` structures
    the layout engine consumes. Returns ``None`` when the process has no stages
    yet, so the caller can fall back to the linear stage view. Rendering (width
    splitting, styling) is the renderer's responsibility.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        A ``(stages, components)`` tuple, or ``None`` if there are no stages.
    """
    stages = await list_stages_for_process(process_id, env, verbose)
    if not stages:
        return None

    stage_inputs: list[StageInput] = []
    for stage in stages:
        links = await list_stage_components(UUID(str(stage.id)), env, verbose)
        stage_inputs.append(
            StageInput(
                name=stage.name,
                number=stage.number,
                stage_components=[
                    StageComponentInput(
                        component_id=str(link.component_id),
                        component_type=link.component_type,
                    )
                    for link in links
                ],
            )
        )

    component_inputs: list[ComponentInput] = []
    for component in await list_components_for_process(process_id, env, verbose):
        component_inputs.append(
            ComponentInput(
                id=str(component.id),
                display_name=await component_display_name(component, env, verbose),
                control_strategy_role=component.control_strategy_role,
                is_isolated=component.is_isolated,
            )
        )

    return stage_inputs, component_inputs


async def get_unconnected_component_names(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[str]:
    """Return display names of process components not assigned to any stage.

    A component "in the process graph" is one referenced by at least one stage
    as a reactant or product. Components created at the process level but never
    assigned to a stage are orphans, returned here so the route view can warn
    about them. The role (e.g. ``"CRUDE"``) is appended when present.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        Display names of unconnected components (empty when all are assigned).
    """
    linked_ids: set[str] = set()
    for stage in await list_stages_for_process(process_id, env, verbose):
        for link in await list_stage_components(UUID(str(stage.id)), env, verbose):
            linked_ids.add(str(link.component_id))

    names: list[str] = []
    for component in await list_components_for_process(process_id, env, verbose):
        if str(component.id) in linked_ids:
            continue
        name = await component_display_name(component, env, verbose)
        if component.control_strategy_role:
            name = f"{name} ({component.control_strategy_role})"
        names.append(name)
    return names


async def get_route_risk_summary(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[dict[str, str | int | None]]:
    """Collect all stage risks for a process and annotate with stage names.

    Fetches each stage in the process, then fetches risks for each stage,
    injecting the ``stage_name`` key so the risk dashboard can display context.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        A list of risk dicts with an additional ``"stage_name"`` key.
    """
    stages = await list_stages_for_process(process_id, env, verbose)
    all_risks: list[dict[str, str | int | None]] = []
    for stage in stages:
        risks = await list_risks_for_stage(UUID(str(stage.id)), env, verbose)
        for risk in risks:
            all_risks.append(
                {
                    "name": risk.name,
                    "risk_type": risk.risk_type,
                    "current_level": risk.current_level,
                    "mitigated_level": risk.mitigated_level,
                    "stage_name": stage.name,
                }
            )
    return sorted(all_risks, key=lambda r: r.get("current_level") or 0, reverse=True)
