"""Risk-table rendering helpers for the REPL."""

from __future__ import annotations

from typing import Any

from ...model.severity import format_level
from .tables import Column, render_table


async def render_risk_table(
    risks: list[dict[str, Any]],
    scope_label: str,
    *,
    width: int = 80,
) -> list[str]:
    """Return display lines for Risk Mode.

    Args:
        risks: Risk dictionaries to render.
        scope_label: Human-readable scope label.
        width: Terminal width; the table is shrunk to fit it.

    Returns:
        Renderable output lines: a title line, a blank line, then either the
        empty-state notice or a box-drawn table of risks.
    """
    title = f"Risks · {scope_label}"
    if not risks:
        return [title, "", "(no risks recorded)"]

    columns = [
        Column("#", align="right"),
        Column("Type"),
        Column("Name"),
        Column("Level"),
        Column("Mitigated"),
        Column("Scope"),
    ]
    rows = [
        [
            str(index),
            str(risk.get("risk_type") or ""),
            str(risk.get("name") or ""),
            format_level(_as_level(risk.get("current_level"))),
            format_level(_as_level(risk.get("mitigated_level"))),
            str(risk.get("scope") or scope_label),
        ]
        for index, risk in enumerate(risks, start=1)
    ]
    # The risk table is drawn un-indented; only the screen inset is reserved.
    return [title, "", *render_table(columns, rows, max_width=width - 2)]


def _as_level(value: Any) -> int | None:
    """Coerce a risk-dict level cell to ``int`` or ``None`` for formatting."""
    return value if isinstance(value, int) else None
