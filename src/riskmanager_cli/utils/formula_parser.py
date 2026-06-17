"""
Molecular formula parsing helpers.

Provides lightweight utilities for extracting and formatting molecular formula
information from SMILES strings and material names, used by the
``visualization_operations`` module and the route layout engine.

Why this exists:
    RDKit is used for SMILES canonicalization and validation, but lightweight
    formula-level text formatting (e.g. subscript rendering in terminal output)
    does not require RDKit and is isolated here to keep operations code clean.
"""

import re


def subscript_formula(formula: str) -> str:
    """Convert numeric digits in a molecular formula to Unicode subscripts.

    Renders a formula like ``"C9H8O4"`` as ``"C₉H₈O₄"`` for cleaner
    terminal display.

    Args:
        formula: Molecular formula string (e.g. ``"C9H8O4"``).

    Returns:
        The formula with digit characters replaced by their Unicode subscript
        equivalents.
    """
    subscripts = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
    return formula.translate(subscripts)


_SUBSCRIPTS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def render_chemical_formula(text: str) -> str:
    """Render a chemical display name with stoichiometric digits subscripted.

    A digit run is treated as a subscript only when it is shorter than four
    digits and the character immediately preceding it is part of a formula unit
    — a letter or a closing bracket (``)``, ``]``, ``}``). Digit runs of four or
    more digits are treated as full-size identifiers (e.g. compound codes like
    ``AZD9291``), and runs following an adduct separator (``·``, ``.``, ``-``),
    a comma, whitespace, or the start of the string are also left full-size,
    because there they are multipliers (hydrate/adduct coefficients) or organic
    locants rather than atom counts.

    Examples:
        ``H2SO4`` → ``H₂SO₄``; ``(NH4)2CO3`` → ``(NH₄)₂CO₃``;
        ``K2HPO4.3H2O`` → ``K₂HPO₄.3H₂O`` (the hydrate ``3`` stays full-size);
        ``AZD9291`` is returned unchanged; ``18-crown-6`` is returned unchanged.

    Why this exists:
        ``interpret_chemically`` display names are free text, so an arbitrary
        formula can appear. This rule is deterministic and never mis-subscripts
        an organic locant or a hydrate coefficient. Stoichiometric subscripts in
        this domain never reach four digits, so the length cap cleanly keeps
        compound codes (``AZD9291``, ``AZ12345678``) full-size without affecting
        real formulas. It deliberately does NOT handle ionic charges/superscripts
        or isotope mass numbers — those are ambiguous to detect from free text
        (``-`` is also a hyphen) and are deferred to a follow-up. This is not a
        complete chemical typesetter.

    Args:
        text: The display name to render.

    Returns:
        The display name with stoichiometric digit runs converted to Unicode
        subscripts; all other characters are returned unchanged.
    """
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isdigit():
            start = index
            while index < length and text[index].isdigit():
                index += 1
            run = text[start:index]
            prev = text[start - 1] if start > 0 else ""
            # The whole digit run is a subscript only when it is short (< 4
            # digits) and directly follows a formula unit (element symbol or
            # closing bracket); otherwise it is a coefficient/locant or a compound
            # code (e.g. AZD9291) and stays full-size.
            subscript = len(run) < 4 and bool(prev) and (prev.isalpha() or prev in ")]}")
            out.append(run.translate(_SUBSCRIPTS) if subscript else run)
            continue
        out.append(char)
        index += 1
    return "".join(out)


def extract_atom_counts(formula: str) -> dict[str, int]:
    """Parse a simple molecular formula string into an atom-count mapping.

    Handles formulae of the form ``"C9H8O4"`` where each element symbol is
    followed by an optional integer count. Does not handle parentheses,
    brackets, or isotopes.

    Args:
        formula: A simple molecular formula string (e.g. ``"C9H8O4"``).

    Returns:
        A ``dict`` mapping element symbol to count.  Elements without an
        explicit count are assigned a count of ``1``.

    Example:
        >>> extract_atom_counts("C9H8O4")
        {'C': 9, 'H': 8, 'O': 4}
    """
    pattern = r"([A-Z][a-z]?)(\d*)"
    return {
        symbol: int(count) if count else 1
        for symbol, count in re.findall(pattern, formula)
        if symbol
    }
