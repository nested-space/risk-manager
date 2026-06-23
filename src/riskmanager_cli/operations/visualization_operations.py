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

from dataclasses import dataclass
from uuid import UUID

from ..config.settings import Environment
from ..model.tables import ComponentRisk, ManufacturingProcessRisk, StageRisk
from ..utils.component_graph_layout import (
    ComponentInput,
    StageComponentInput,
    StageInput,
)
from .component_operations import component_display_name, list_components_for_process
from .component_risks_operations import list_risks_for_component
from .manufacturing_process_risk_operations import list_risks_for_process
from .stage_component_operations import list_stage_components
from .stage_operations import list_stages_for_process
from .stage_risk_operations import list_risks_for_stage


@dataclass
class AggregatedRouteRisk:
    """One risk gathered from anywhere in a route, tagged with its source.

    Attributes:
        source: Where the risk lives — ``"Stage"``, ``"Component"``, or
            ``"Process"``.
        entity_name: The owning stage or component's display name; ``"—"`` for
            process-level risks, which have no sub-entity.
        risk_type: The risk category (e.g. ``"Safety"``).
        current_level: Unmitigated severity (1-5), or ``None``.
        name: The risk title.
        proposed_mitigation: Planned mitigation, or ``None``.
        mitigated_level: Projected severity after mitigation (1-5), or ``None``.
    """

    source: str
    entity_name: str
    risk_type: str
    current_level: int | None
    name: str
    proposed_mitigation: str | None
    mitigated_level: int | None


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


async def get_aggregated_route_risks(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> list[AggregatedRouteRisk]:
    """Collect every risk in a route — stage, component, and process-level.

    Walks the process's stages and components, fanning out to each one's risks,
    then appends the process-level risks. Each row is tagged with its ``source``
    and owning ``entity_name`` so the route view can present a single table.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        All route risks, sorted by ``current_level`` descending.
    """
    risks: list[AggregatedRouteRisk] = []

    for stage in await list_stages_for_process(process_id, env, verbose):
        for stage_risk in await list_risks_for_stage(UUID(str(stage.id)), env, verbose):
            risks.append(_aggregate(stage_risk, "Stage", stage.name))

    for component in await list_components_for_process(process_id, env, verbose):
        entity_name = await component_display_name(component, env, verbose)
        for component_risk in await list_risks_for_component(UUID(str(component.id)), env, verbose):
            risks.append(_aggregate(component_risk, "Component", entity_name))

    for process_risk in await list_risks_for_process(process_id, env, verbose):
        risks.append(_aggregate(process_risk, "Process", "—"))

    return sorted(risks, key=lambda r: r.current_level or 0, reverse=True)


def _aggregate(
    risk: StageRisk | ComponentRisk | ManufacturingProcessRisk,
    source: str,
    entity_name: str,
) -> AggregatedRouteRisk:
    """Tag a risk record with its ``source`` and owning ``entity_name``."""
    return AggregatedRouteRisk(
        source=source,
        entity_name=entity_name,
        risk_type=risk.risk_type,
        current_level=risk.current_level,
        name=risk.name,
        proposed_mitigation=risk.proposed_mitigation,
        mitigated_level=risk.mitigated_level,
    )
