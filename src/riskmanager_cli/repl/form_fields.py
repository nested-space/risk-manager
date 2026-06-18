"""Shared guided-prompt field options and value coercers.

These small, stateless helpers are used by every screen that opens a guided
prompt: the select-field option lists, an enum→options builder, and the coercers
that turn the prompt's raw string answers back into typed values. They live here
(rather than on any one screen) so the screens and the dispatcher share a single
definition without an import cycle.
"""

from __future__ import annotations

from enum import Enum

#: Yes/No options for required boolean ``select`` fields.
BOOL_OPTIONS: list[tuple[str, str]] = [("Yes", "true"), ("No", "false")]

#: Yes/No options for optional boolean ``select`` fields, with an unset choice
#: that stores an empty string (coerced to ``None`` downstream).
OPTIONAL_BOOL_OPTIONS: list[tuple[str, str]] = [("Not specified", ""), *BOOL_OPTIONS]

#: Allowed component-type values for stage-component links.
COMPONENT_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("reactant", "reactant"),
    ("product", "product"),
]

#: No/Yes options for confirmation prompts, defaulting to the safe "No" choice.
CONFIRM_OPTIONS: list[tuple[str, str]] = [("No", "no"), ("Yes", "yes")]

#: Yes/No options for the home quit confirmation, defaulting to "Yes".
QUIT_OPTIONS: list[tuple[str, str]] = [("Yes", "yes"), ("No", "no")]


def enum_options(enum_cls: type[Enum]) -> list[tuple[str, str]]:
    """Return ``(label, value)`` select options for a string enum.

    Args:
        enum_cls: The enum to enumerate. Members must have string values.

    Returns:
        One ``(value, value)`` pair per member, in definition order.
    """
    return [(str(member.value), str(member.value)) for member in enum_cls]


def optional_int(value: str | None) -> int | None:
    """Parse *value* as an int, or ``None`` when it is empty/``None``."""
    if value is None or value == "":
        return None
    return int(value)


def optional_float(value: str | None) -> float | None:
    """Parse *value* as a float, or ``None`` when it is empty/``None``."""
    if value is None or value == "":
        return None
    return float(value)


def optional_bool(value: str | None) -> bool | None:
    """Parse *value* as a tri-state bool, or ``None`` when it is empty/``None``."""
    if value is None or value == "":
        return None
    return value.strip().lower() in {"1", "true", "yes", "y"}


def as_bool(value: str | None) -> bool:
    """Parse *value* as a bool, treating empty/``None`` as ``False``."""
    return (value or "false").strip().lower() in {"1", "true", "yes", "y"}


def default_text(value: object) -> str | None:
    """Return *value* as display text, or ``None`` for empty/unset values."""
    if value in {None, ""}:
        return None
    return str(value)
