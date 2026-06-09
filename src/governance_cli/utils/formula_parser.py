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
