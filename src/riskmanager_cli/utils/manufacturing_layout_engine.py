"""
Risk-summary helpers for the manufacturing route view.

Formats a process's risks into a compact, terminal-renderable dashboard for the
route view output pane. Used by the route view renderer
(``repl/renderers/route_renderer.py``).

Why this exists:
    The route view is the primary working mode of the REPL. Keeping the
    risk-summary formatting here as a pure utility separates the presentation
    logic from the rendering logic, making both independently testable.
"""

from ..model.severity import SEVERITY_BY_LEVEL

# Risk value type alias: maps field names to primitive scalar values.
RiskDict = dict[str, str | int | float | bool | None]


# Risk level → uppercase display label, derived from the shared 1-5 scale.
_LEVEL_LABELS: dict[int, str] = {level: name.upper() for level, name in SEVERITY_BY_LEVEL.items()}


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


def render_risk_summary(
    risks: list[RiskDict], max_rows: int = 5, *, include_header: bool = True
) -> list[str]:
    """Render a compact risk dashboard for the route view output pane.

    Shows the top *max_rows* risks by current level (descending), formatted as::

        ⚠ Risk Dashboard
        [CRITICAL] Explosion hazard — Stage 1: Reaction
        [HIGH]     Solvent toxicity  — Stage 2: Purification

    Args:
        risks: List of risk dicts with keys: ``name``, ``current_level``,
            ``risk_type``, and optionally ``stage_name`` or ``component_name``.
        max_rows: Maximum number of risks to display. Defaults to 5.
        include_header: When ``True`` (default) prepend the ``⚠ Risk Dashboard``
            header line; callers that supply their own section heading pass
            ``False`` to omit it.

    Returns:
        A list of strings ready for display in the output pane.
    """
    if not risks:
        return ["  (no risks recorded)"]

    sorted_risks = sorted(risks, key=_risk_level, reverse=True)[:max_rows]
    lines = ["⚠ Risk Dashboard"] if include_header else []
    for r in sorted_risks:
        level = _risk_level(r)
        label = _LEVEL_LABELS.get(level, "INFO")
        name = str(r.get("name", "Unknown"))
        lines.append(f"  [{label:<10}] {name}{_risk_context(r)}")

    return lines
