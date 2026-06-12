"""Canonical risk-severity scale shared across schemas, prompts, and renderers.

Risk ``current_level`` / ``mitigated_level`` use a single 1-5 ordinal scale where
the number *is* the severity rank: ``5`` is the most severe. Keeping the
level->name mapping, the display format, and the prompt options in one leaf
module (no project imports) means every consumer agrees on what a level means
and renders it identically.

Why this exists:
    Three render sites previously disagreed on the scale (the project summary,
    the risk table, and the manufacturing diagram each used a different 1-10
    bucketing). This module is the single source of truth they now share.
"""

from __future__ import annotations

#: Ordinal severity scale: ``level -> name``, most severe first.
SEVERITY_BY_LEVEL: dict[int, str] = {
    5: "Critical",
    4: "High",
    3: "Medium",
    2: "Low",
    1: "Negligible",
}

#: Inclusive bounds of the valid level range.
MIN_LEVEL = 1
MAX_LEVEL = 5

#: Placeholder shown when a level is missing or outside the valid range.
_UNKNOWN = "-"

#: ``(label, stored value)`` options for a ``select`` prompt field, most severe
#: first so the dropdown defaults to ``Critical``. The label matches
#: :func:`format_level` so the choice reads the same in the form and the table.
LEVEL_OPTIONS: list[tuple[str, str]] = [
    (f"{name} ({level})", str(level)) for level, name in SEVERITY_BY_LEVEL.items()
]


def severity_name(level: int | None) -> str:
    """Return the severity name for *level* (e.g. ``"Critical"``).

    Args:
        level: A risk level, or ``None``.

    Returns:
        The matching severity name, or ``"-"`` when *level* is ``None`` or
        outside the 1-5 range (e.g. legacy data on the old 1-10 scale).
    """
    return SEVERITY_BY_LEVEL.get(level, _UNKNOWN) if level is not None else _UNKNOWN


def format_level(level: int | None) -> str:
    """Return the display form for *level*, e.g. ``"Critical (5)"``.

    Args:
        level: A risk level, or ``None``.

    Returns:
        ``"{name} ({level})"`` for a valid level, otherwise ``"-"``.
    """
    name = severity_name(level)
    return f"{name} ({level})" if name != _UNKNOWN else _UNKNOWN
