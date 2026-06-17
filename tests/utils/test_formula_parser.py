"""Unit tests for riskmanager_cli.utils.formula_parser."""

import pytest

from riskmanager_cli.utils.formula_parser import render_chemical_formula


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Category A — stoichiometric subscripts after element/group/bracket.
        ("H2SO4", "H₂SO₄"),
        ("(NH4)2CO3", "(NH₄)₂CO₃"),
        ("K3[Fe(CN)6]", "K₃[Fe(CN)₆]"),
        ("AlCl3", "AlCl₃"),
        ("C10H22", "C₁₀H₂₂"),  # multi-digit run stays a single subscript
    ],
)
def test_render_chemical_formula_subscripts_stoichiometry(text: str, expected: str) -> None:
    """Digit runs following an element or closing bracket become subscripts."""
    assert render_chemical_formula(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Category B — adduct/hydrate coefficients stay full-size; inner counts subscript.
        ("K2HPO4.3H2O", "K₂HPO₄.3H₂O"),
        ("NaOAc·3H2O", "NaOAc·3H₂O"),
        ("Na2B4O7.10H2O", "Na₂B₄O₇.10H₂O"),
        ("CuSO4·5H2O", "CuSO₄·5H₂O"),
        ("BF3·Et2O", "BF₃·Et₂O"),
        ("2KCl·MgCl2", "2KCl·MgCl₂"),  # leading coefficient stays full-size
    ],
)
def test_render_chemical_formula_keeps_coefficients_full_size(text: str, expected: str) -> None:
    """Digit runs after an adduct separator or at the start are not subscripted."""
    assert render_chemical_formula(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        # Compound codes: a digit run of 4+ digits is an identifier, not a
        # subscript, even though it follows a letter.
        "AZD9291",
        "AZD1234",
        "AZ12345678",
    ],
)
def test_render_chemical_formula_keeps_compound_codes_full_size(text: str) -> None:
    """Digit runs of four or more digits are treated as codes, never subscripts."""
    assert render_chemical_formula(text) == text


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        # Boundary cases that must pass through unchanged (deferred scope).
        "18-crown-6",  # organic locants
        "tert-butyl",
        "p-cymene",
        "Na+",  # charges are out of scope — no superscripting
        "SO4 3-",
        "",
    ],
)
def test_render_chemical_formula_leaves_non_formula_digits_untouched(text: str) -> None:
    """Locants, hyphenated names, and charges are returned unchanged."""
    # Charges/locants must NOT gain subscripts; the only legitimate change here
    # would be a stoichiometric subscript, of which these strings have none after
    # an element symbol — except "SO4 3-" whose "4" follows "O" and so subscripts.
    expected = "SO₄ 3-" if text == "SO4 3-" else text
    assert render_chemical_formula(text) == expected
