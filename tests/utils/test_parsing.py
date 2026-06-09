"""Unit tests for riskmanager_cli.utils.parsing."""

import pytest

from riskmanager_cli.utils.parsing import detect_delimiter, parse_csv_rows, split_aliases


@pytest.mark.unit
def test_detect_delimiter_returns_comma_for_csv() -> None:
    """Comma-only CSV selects comma delimiter."""
    assert detect_delimiter("name,smiles,alias\nAspirin,CC(=O)Oc1ccccc1C(=O)O,ASA") == ","


@pytest.mark.unit
def test_detect_delimiter_returns_semicolon_when_more_prevalent() -> None:
    """Semicolons outnumbering commas selects semicolon delimiter."""
    assert detect_delimiter("name;smiles;alias\nAspirin;CC(=O)Oc1ccccc1;ASA") == ";"


@pytest.mark.unit
def test_detect_delimiter_defaults_to_comma_when_equal() -> None:
    """Equal counts of semicolons and commas defaults to comma."""
    assert detect_delimiter("a,b;c,d;") == ","


@pytest.mark.unit
def test_parse_csv_rows_returns_dicts_for_comma_csv() -> None:
    """Comma-delimited CSV with a header row yields row dicts."""
    content = "name,smiles\nAspirin,CC(=O)O\n"
    rows = list(parse_csv_rows(content))
    assert len(rows) == 1
    assert rows[0]["name"] == "Aspirin"
    assert rows[0]["smiles"] == "CC(=O)O"


@pytest.mark.unit
def test_parse_csv_rows_returns_dicts_for_semicolon_csv() -> None:
    """Semicolon-delimited CSV is parsed when semicolons dominate."""
    content = "name;smiles\nAspirin;CC(=O)O\n"
    rows = list(parse_csv_rows(content))
    assert len(rows) == 1
    assert rows[0]["name"] == "Aspirin"


@pytest.mark.unit
def test_parse_csv_rows_skips_all_empty_rows() -> None:
    """Rows where all values are empty are skipped."""
    content = "name,smiles\nAspirin,CC(=O)O\n,\n"
    rows = list(parse_csv_rows(content))
    assert len(rows) == 1


@pytest.mark.unit
def test_parse_csv_rows_strips_whitespace_from_values() -> None:
    """Leading and trailing whitespace is stripped from row values."""
    content = "name , smiles\n  Aspirin  ,  CC(=O)O  \n"
    rows = list(parse_csv_rows(content))
    assert rows[0]["name"] == "Aspirin"
    assert rows[0]["smiles"] == "CC(=O)O"


@pytest.mark.unit
def test_split_aliases_returns_list_from_semicolon_string() -> None:
    """Semicolon-joined aliases are split into a list."""
    result = split_aliases("Aspirin;ASA;Acetylsalicylic acid")
    assert result == ["Aspirin", "ASA", "Acetylsalicylic acid"]


@pytest.mark.unit
def test_split_aliases_empty_string_returns_empty_list() -> None:
    """An empty string yields an empty list."""
    assert split_aliases("") == []


@pytest.mark.unit
def test_split_aliases_strips_whitespace_around_entries() -> None:
    """Whitespace around individual aliases is stripped."""
    result = split_aliases("  Aspirin  ;  ASA  ")
    assert result == ["Aspirin", "ASA"]


@pytest.mark.unit
def test_split_aliases_skips_empty_segments() -> None:
    """Empty segments between separators are excluded."""
    result = split_aliases("Aspirin;;ASA")
    assert result == ["Aspirin", "ASA"]


@pytest.mark.unit
def test_split_aliases_custom_separator() -> None:
    """Custom separator is applied when provided."""
    result = split_aliases("Aspirin|ASA", separator="|")
    assert result == ["Aspirin", "ASA"]
