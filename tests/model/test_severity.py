"""Unit tests for the canonical risk-severity scale."""

import pytest

from riskmanager_cli.model.severity import (
    LEVEL_OPTIONS,
    MAX_LEVEL,
    MIN_LEVEL,
    SEVERITY_BY_LEVEL,
    format_level,
    severity_name,
)


@pytest.mark.unit
def test_scale_is_1_to_5_most_severe_first() -> None:
    """The scale runs 1-5 with 5 = Critical, ordered most severe first."""
    assert (MIN_LEVEL, MAX_LEVEL) == (1, 5)
    assert list(SEVERITY_BY_LEVEL.items()) == [
        (5, "Critical"),
        (4, "High"),
        (3, "Medium"),
        (2, "Low"),
        (1, "Negligible"),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("level", "name"),
    [(5, "Critical"), (4, "High"), (3, "Medium"), (2, "Low"), (1, "Negligible")],
)
def test_severity_name_maps_each_level(level: int, name: str) -> None:
    """Every valid level resolves to its severity name."""
    assert severity_name(level) == name


@pytest.mark.unit
@pytest.mark.parametrize("level", [None, 0, 6, 10])
def test_severity_name_unknown_for_out_of_range(level: int | None) -> None:
    """``None`` and out-of-range levels (e.g. legacy 1-10) resolve to ``-``."""
    assert severity_name(level) == "-"


@pytest.mark.unit
def test_format_level_labels_with_number() -> None:
    """A valid level renders as ``Name (n)``; invalid ones render as ``-``."""
    assert format_level(5) == "Critical (5)"
    assert format_level(2) == "Low (2)"
    assert format_level(None) == "-"
    assert format_level(9) == "-"


@pytest.mark.unit
def test_level_options_match_format_and_store_numbers() -> None:
    """Dropdown labels match :func:`format_level` and store the bare number."""
    assert LEVEL_OPTIONS == [
        ("Critical (5)", "5"),
        ("High (4)", "4"),
        ("Medium (3)", "3"),
        ("Low (2)", "2"),
        ("Negligible (1)", "1"),
    ]
