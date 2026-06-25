"""Unit tests for the canonical risk-severity scale."""

import pytest

from riskmanager_cli.model.severity import (
    LEVEL_OPTIONS,
    MAX_LEVEL,
    MIN_LEVEL,
    SEVERITY_BY_LEVEL,
    format_level,
    severity_abbr,
    severity_name,
)


@pytest.mark.unit
def test_scale_is_1_to_5_most_severe_first() -> None:
    """The scale runs 1-5 with 5 = Very High, ordered most severe first."""
    assert (MIN_LEVEL, MAX_LEVEL) == (1, 5)
    assert list(SEVERITY_BY_LEVEL.items()) == [
        (5, "Very High"),
        (4, "High"),
        (3, "Medium"),
        (2, "Low"),
        (1, "Very Low"),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("level", "name"),
    [(5, "Very High"), (4, "High"), (3, "Medium"), (2, "Low"), (1, "Very Low")],
)
def test_severity_name_maps_each_level(level: int, name: str) -> None:
    """Every valid level resolves to its severity name."""
    assert severity_name(level) == name


@pytest.mark.unit
@pytest.mark.parametrize(
    ("level", "abbr"),
    [(5, "VH"), (4, "H"), (3, "M"), (2, "L"), (1, "VL")],
)
def test_severity_abbr_maps_each_level(level: int, abbr: str) -> None:
    """Every valid level resolves to its compact column code."""
    assert severity_abbr(level) == abbr


@pytest.mark.unit
@pytest.mark.parametrize("level", [None, 0, 6, 10])
def test_severity_name_unknown_for_out_of_range(level: int | None) -> None:
    """``None`` and out-of-range levels (e.g. legacy 1-10) resolve to ``-``."""
    assert severity_name(level) == "-"
    assert severity_abbr(level) == "-"


@pytest.mark.unit
def test_format_level_uses_abbreviation_with_number() -> None:
    """A valid level renders as the compact ``ABBR (n)``; invalid ones as ``-``."""
    assert format_level(5) == "VH (5)"
    assert format_level(2) == "L (2)"
    assert format_level(None) == "-"
    assert format_level(9) == "-"


@pytest.mark.unit
def test_level_options_spell_out_full_names_and_store_numbers() -> None:
    """Dropdown labels spell out the full severity name and store the bare number."""
    assert LEVEL_OPTIONS == [
        ("Very High (5)", "5"),
        ("High (4)", "4"),
        ("Medium (3)", "3"),
        ("Low (2)", "2"),
        ("Very Low (1)", "1"),
    ]
