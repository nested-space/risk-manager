"""
Visualization operations for manufacturing route ASCII layout.

Bridges the operations layer (database queries) with the layout engine
(``utils/manufacturing_layout_engine.py``) to produce printable route diagrams.
Used by the route view renderer (``repl/renderers/route_renderer.py``).

Why this exists:
    The layout engine is a pure utility that knows nothing about the database.
    This module fetches the required data and converts it into the ``StageNode``
    objects that the layout engine consumes.
"""

from uuid import UUID

from ..config.settings import Environment
from ..utils.manufacturing_layout_engine import LayoutResult, StageNode, render_route_layout
from .stage_operations import list_stages_for_process
from .stage_risk_operations import list_risks_for_stage


async def get_route_layout(
    process_id: UUID,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> LayoutResult:
    """Fetch stages for *process_id* and render an ASCII route diagram.

    Args:
        process_id: UUID of the manufacturing process.
        env: Database environment.
        verbose: If ``True``, prints the database path.

    Returns:
        A :class:`~..utils.manufacturing_layout_engine.LayoutResult` with
        rendered ASCII lines. Returns an empty-stage layout if no stages exist.
    """
    stages = await list_stages_for_process(process_id, env, verbose)
    nodes = [StageNode(name=s.name, number=s.number) for s in stages]
    return render_route_layout(nodes)


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
