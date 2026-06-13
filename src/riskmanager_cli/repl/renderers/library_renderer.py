"""Render library track screens for materials, NCRM, and counterions."""

from __future__ import annotations

from typing import Any


async def render_library_screen(
    sub_mode: str,
    items: list[dict[str, Any]],
) -> list[str]:
    """Return display lines for the Library track.

    Args:
        sub_mode: Active library sub-mode.
        items: Library rows already converted to dictionaries.

    Returns:
        Renderable output lines.
    """
    if sub_mode == "select":
        return [
            "Library",
            "",
            "Choose a subsection:",
            "  /library materials",
            "  /library ncrm",
            "  /library counterions",
        ]

    title = f"Library · {sub_mode}"
    lines = [title, ""]
    if not items:
        lines.append("(no items found)")
        return lines

    for index, item in enumerate(items, start=1):
        name = str(item.get("display_name") or item.get("name") or item.get("id") or "Unknown")
        secondary = item.get("name") or item.get("smiles") or ""
        if isinstance(secondary, bool):
            secondary = "yes" if secondary else "no"
        # Hide the secondary line when it merely repeats the primary label
        # (e.g. display_name defaulted to name).
        detail = f" — {secondary}" if secondary and str(secondary) != name else ""
        lines.append(f"{index:>2}. {name}{detail}")
    return lines
