"""
ASCII layout engine for manufacturing route visualisation.

Generates terminal-renderable ASCII diagrams of manufacturing processes,
showing stages connected by arrows and annotated with stage names and numbers.
Used by the route view renderer (``repl/renderers/route_renderer.py``).

Why this exists:
    The route view is the primary working mode of the REPL. A dedicated layout
    engine separates the visual calculation logic from the rendering logic,
    making both independently testable.
"""

from dataclasses import dataclass, field

# Risk value type alias: maps field names to primitive scalar values.
RiskDict = dict[str, str | int | float | bool | None]


@dataclass
class StageNode:
    """A stage in the layout graph.

    Attributes:
        name: Display name of the stage.
        number: Sequence number within the process.
        risk_count: Number of risks associated with this stage (for annotation).
    """

    name: str
    number: int
    risk_count: int = 0


@dataclass
class LayoutResult:
    """Result of laying out a manufacturing route as ASCII art.

    Attributes:
        lines: List of strings; each string is one rendered terminal row.
        width: Character width of the widest line.
    """

    lines: list[str] = field(default_factory=list)
    width: int = 0


def _truncate(text: str, max_len: int) -> str:
    """Truncate *text* to *max_len* characters, adding ``…`` if truncated.

    Args:
        text: Input string to truncate.
        max_len: Maximum number of characters allowed.

    Returns:
        The original string if it fits; otherwise the first ``(max_len - 1)``
        characters followed by ``"…"``.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _join_row(cells: list[str], connectors: list[str], fill: str) -> str:
    """Join *cells* with *connectors* (or *fill* for the last cell) into a row.

    Args:
        cells: One string cell per stage.
        connectors: One connector string per stage; empty string for the last.
        fill: Whitespace string used after the last cell (same width as a connector).

    Returns:
        A single stripped row string.
    """
    parts = [cell + (conn or fill) for cell, conn in zip(cells, connectors)]
    return "".join(parts).rstrip()


def _build_diagram_rows(
    stages: list[StageNode],
    inner: int,
    connector: str,
) -> list[str]:
    """Build the four text rows of the stage diagram.

    Args:
        stages: Ordered list of :class:`StageNode` objects.
        inner: Interior width of each stage box.
        connector: Arrow connector between adjacent boxes.

    Returns:
        A list of four row strings: top border, name, stage number, bottom border.
    """
    top = f"┌{'─' * (inner + 2)}┐"
    bot = f"└{'─' * (inner + 2)}┘"
    fill = " " * len(connector)
    conns = [connector if i < len(stages) - 1 else "" for i in range(len(stages))]

    tops = [top] * len(stages)
    mids = [f"│ {_truncate(s.name, inner).center(inner)} │" for s in stages]
    nums = [f"│ {f'Stage {s.number}'.center(inner)} │" for s in stages]
    bots = [bot] * len(stages)

    return [
        _join_row(tops, conns, fill),
        _join_row(mids, conns, fill),
        _join_row(nums, conns, fill),
        _join_row(bots, conns, fill),
    ]


def render_route_layout(
    stages: list[StageNode],
    box_width: int = 13,
    connector: str = "───▶",
) -> LayoutResult:
    """Render a linear sequence of stages as a horizontal ASCII diagram.

    Each stage is drawn as a box::

        ┌─────────────┐
        │  Reaction   │
        │  Stage 1    │
        └─────────────┘

    Adjacent stages are connected by ``connector``.

    Args:
        stages: Ordered list of :class:`StageNode` objects to render.
        box_width: Interior width of each stage box (default: 13 characters).
        connector: Arrow string connecting adjacent boxes.

    Returns:
        A :class:`LayoutResult` with the rendered lines and overall width.
    """
    if not stages:
        return LayoutResult(lines=["(no stages)"], width=11)

    lines = _build_diagram_rows(stages, box_width, connector)
    return LayoutResult(lines=lines, width=max(len(line) for line in lines))


# Risk level → display label mapping.
_LEVEL_LABELS: dict[int, str] = {
    10: "CRITICAL",
    9: "CRITICAL",
    8: "HIGH",
    7: "HIGH",
    6: "MEDIUM",
    5: "MEDIUM",
    4: "LOW",
    3: "LOW",
    2: "INFO",
    1: "INFO",
}


def _risk_level(risk: RiskDict) -> int:
    """Extract the integer ``current_level`` from a risk dict.

    Args:
        risk: A risk dict with an optional ``current_level`` key.

    Returns:
        The integer level, or ``0`` if missing or non-integer.
    """
    raw = risk.get("current_level")
    return int(raw) if isinstance(raw, int) else 0


def _risk_context(risk: RiskDict) -> str:
    """Build a context suffix string for a risk row.

    Args:
        risk: A risk dict optionally containing ``stage_name`` or ``component_name``.

    Returns:
        A formatted context string like ``" — Stage: Reaction"``, or ``""``.
    """
    if risk.get("stage_name"):
        return f" — Stage: {risk['stage_name']}"
    if risk.get("component_name"):
        return f" — Component: {risk['component_name']}"
    return ""


def render_risk_summary(risks: list[RiskDict], max_rows: int = 5) -> list[str]:
    """Render a compact risk dashboard for the route view output pane.

    Shows the top *max_rows* risks by current level (descending), formatted as::

        ⚠ Risk Dashboard
        [CRITICAL] Explosion hazard — Stage 1: Reaction
        [HIGH]     Solvent toxicity  — Stage 2: Purification

    Args:
        risks: List of risk dicts with keys: ``name``, ``current_level``,
            ``risk_type``, and optionally ``stage_name`` or ``component_name``.
        max_rows: Maximum number of risks to display. Defaults to 5.

    Returns:
        A list of strings ready for display in the output pane.
    """
    if not risks:
        return ["  (no risks recorded)"]

    sorted_risks = sorted(risks, key=_risk_level, reverse=True)[:max_rows]
    lines = ["⚠ Risk Dashboard"]
    for r in sorted_risks:
        level = _risk_level(r)
        label = _LEVEL_LABELS.get(level, "INFO")
        name = str(r.get("name", "Unknown"))
        lines.append(f"  [{label:<8}] {name}{_risk_context(r)}")

    return lines
