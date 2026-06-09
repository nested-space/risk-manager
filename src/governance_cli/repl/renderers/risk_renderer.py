"""Risk-table rendering helpers for the REPL."""

from __future__ import annotations

from typing import Any

import blessed

_LEVEL_NAMES: dict[int, str] = {
    9: "Critical",
    8: "High",
    6: "Medium",
    0: "Low",
}


async def render_risk_table(
    risks: list[dict[str, Any]],
    scope_label: str,
) -> list[str]:
    """Return display lines for Risk Mode.

    Args:
        risks: Risk dictionaries to render.
        scope_label: Human-readable scope label.

    Returns:
        Renderable output lines.
    """
    term = blessed.Terminal()
    header = f"Risks · {scope_label}"
    lines = [header, "", "#  Type         Name                      Level       Mitigated  Scope"]
    if not risks:
        lines.append("(no risks recorded)")
        return lines

    for index, risk in enumerate(risks, start=1):
        risk_type = str(risk.get("risk_type") or "")[:12]
        name = str(risk.get("name") or "")[:25]
        current_level = _format_level(term, risk.get("current_level"))
        mitigated = _format_numeric(risk.get("mitigated_level"))
        scope = str(risk.get("scope") or scope_label)[:10]
        lines.append(
            f"{index:>2} {risk_type:<12} {name:<25} {current_level:<11} {mitigated:<10} {scope}"
        )
    return lines


def _format_level(term: blessed.Terminal, value: Any) -> str:
    raw_value = value if isinstance(value, int) else 0
    label = next(
        (name for threshold, name in _LEVEL_NAMES.items() if raw_value >= threshold), "Low"
    )
    colour = term.red if label == "Critical" else term.yellow if label == "High" else term.cyan
    return f"{colour}{label}{term.normal}"


def _format_numeric(value: Any) -> str:
    return str(value) if isinstance(value, int) else "-"
