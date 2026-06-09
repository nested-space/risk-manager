"""Unit tests for riskmanager_cli.operations.smiles_operations."""

import pytest

from riskmanager_cli.operations.smiles_operations import (
    canonicalize_smiles,
    detect_search_type,
    is_canonical_smiles,
    is_valid_smiles,
)


@pytest.mark.unit
def test_detect_search_type_returns_id_for_uuid() -> None:
    """Standard UUID4 strings are classified as 'id'."""
    assert detect_search_type("550e8400-e29b-41d4-a716-446655440000") == "id"


@pytest.mark.unit
def test_detect_search_type_returns_id_for_uuid_without_dashes() -> None:
    """UUID without dashes is also classified as 'id'."""
    assert detect_search_type("550e8400e29b41d4a716446655440000") == "id"


@pytest.mark.unit
def test_detect_search_type_returns_smiles_for_parentheses() -> None:
    """Strings containing '(' are classified as 'smiles'."""
    assert detect_search_type("CC(=O)O") == "smiles"


@pytest.mark.unit
def test_detect_search_type_returns_smiles_for_bracket_notation() -> None:
    """Strings containing '[' are classified as 'smiles'."""
    assert detect_search_type("c1ccccc1[OH]") == "smiles"


@pytest.mark.unit
def test_detect_search_type_returns_smiles_for_equals_sign() -> None:
    """Strings containing '=' are classified as 'smiles'."""
    assert detect_search_type("C=C") == "smiles"


@pytest.mark.unit
def test_detect_search_type_returns_name_for_plain_text() -> None:
    """Plain alphabetic text with no SMILES chars is classified as 'name'."""
    assert detect_search_type("Aspirin") == "name"


@pytest.mark.unit
def test_is_valid_smiles_returns_true_for_valid_smiles() -> None:
    """A correctly formed SMILES string is valid."""
    assert is_valid_smiles("CC(=O)O") is True


@pytest.mark.unit
def test_is_valid_smiles_returns_false_for_garbage() -> None:
    """A string that is not valid SMILES returns False."""
    assert is_valid_smiles("NOT_A_SMILES_STRING!!!") is False


@pytest.mark.unit
def test_canonicalize_smiles_returns_string_for_valid_smiles() -> None:
    """A valid SMILES string is returned as its canonical form."""
    result = canonicalize_smiles("CC(=O)O")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
def test_canonicalize_smiles_returns_none_for_invalid_smiles() -> None:
    """An invalid SMILES string produces None."""
    assert canonicalize_smiles("NOT_SMILES") is None


@pytest.mark.unit
def test_is_canonical_smiles_returns_true_when_already_canonical() -> None:
    """A SMILES string that is already canonical returns True."""
    canonical = canonicalize_smiles("CC(=O)O")
    assert canonical is not None
    assert is_canonical_smiles(canonical) is True


@pytest.mark.unit
def test_is_canonical_smiles_returns_false_for_invalid_smiles() -> None:
    """An invalid SMILES string returns False from is_canonical_smiles."""
    assert is_canonical_smiles("NOT_SMILES") is False
