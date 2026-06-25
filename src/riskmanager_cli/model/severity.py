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
    5: "Very High",
    4: "High",
    3: "Medium",
    2: "Low",
    1: "Very Low",
}

#: Compact column codes: ``level -> abbreviation``. The risk tables show these
#: (via :func:`format_level`) so the Level/Mitigated cells stay narrow and a
#: consistent width; the full :data:`SEVERITY_BY_LEVEL` names are reserved for
#: the prompt dropdown and the project summary, which have room for them.
SEVERITY_ABBR_BY_LEVEL: dict[int, str] = {
    5: "VH",
    4: "H",
    3: "M",
    2: "L",
    1: "VL",
}

#: Inclusive bounds of the valid level range.
MIN_LEVEL = 1
MAX_LEVEL = 5

#: Placeholder shown when a level is missing or outside the valid range.
_UNKNOWN = "-"

#: ``(label, stored value)`` options for a ``select`` prompt field, most severe
#: first so the dropdown defaults to ``Very High``. The label spells out the full
#: severity name (e.g. ``"Very High (5)"``) for clarity when choosing, while the
#: tables show the abbreviation from :func:`format_level`.
LEVEL_OPTIONS: list[tuple[str, str]] = [
    (f"{name} ({level})", str(level)) for level, name in SEVERITY_BY_LEVEL.items()
]


def severity_name(level: int | None) -> str:
    """Return the full severity name for *level* (e.g. ``"Very High"``).

    Args:
        level: A risk level, or ``None``.

    Returns:
        The matching severity name, or ``"-"`` when *level* is ``None`` or
        outside the 1-5 range (e.g. legacy data on the old 1-10 scale).
    """
    return SEVERITY_BY_LEVEL.get(level, _UNKNOWN) if level is not None else _UNKNOWN


def severity_abbr(level: int | None) -> str:
    """Return the compact severity code for *level* (e.g. ``"VH"``).

    Args:
        level: A risk level, or ``None``.

    Returns:
        The matching abbreviation, or ``"-"`` when *level* is ``None`` or
        outside the 1-5 range.
    """
    return SEVERITY_ABBR_BY_LEVEL.get(level, _UNKNOWN) if level is not None else _UNKNOWN


def format_level(level: int | None) -> str:
    """Return the compact table display for *level*, e.g. ``"VH (5)"``.

    Uses the abbreviation (not the full name) so the Level/Mitigated columns stay
    narrow and a consistent width across rows.

    Args:
        level: A risk level, or ``None``.

    Returns:
        ``"{abbr} ({level})"`` for a valid level, otherwise ``"-"``.
    """
    abbr = severity_abbr(level)
    return f"{abbr} ({level})" if abbr != _UNKNOWN else _UNKNOWN
