"""
CSV parsing helpers for bulk import operations.

Provides utilities for reading and validating CSV data used by
``/admin import`` commands. Supports both comma and semicolon delimiters
with automatic detection.

Why this exists:
    Bulk import CSV files may come from different sources (Excel exports,
    hand-edited files) with varying delimiter conventions. Centralising
    delimiter detection and row validation here reduces duplication across
    the 9 import command handlers.
"""

import csv
import io
from collections.abc import Iterator


def detect_delimiter(sample: str) -> str:
    """Detect the CSV delimiter used in *sample* text.

    Checks whether the sample contains more semicolons or commas and returns
    the more prevalent one. Falls back to comma if counts are equal.

    Args:
        sample: A string containing one or more lines of CSV text.

    Returns:
        ``";"`` if semicolons are more prevalent, otherwise ``","``.
    """
    comma_count = sample.count(",")
    semicolon_count = sample.count(";")
    return ";" if semicolon_count > comma_count else ","


def parse_csv_rows(content: str) -> Iterator[dict[str, str]]:
    """Parse CSV *content* into a sequence of row dicts.

    Automatically detects the delimiter from the first 1 024 characters.
    Strips leading/trailing whitespace from all field values. Skips rows
    where all values are empty.

    Args:
        content: Full CSV file content as a string (UTF-8 decoded).

    Yields:
        One ``dict[str, str]`` per data row; keys are the header field names
        (stripped and lowercased). Empty rows are skipped.
    """
    sample = content[:1024]
    delimiter = detect_delimiter(sample)
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    for row in reader:
        cleaned = {k.strip().lower(): v.strip() for k, v in row.items() if k}
        if any(cleaned.values()):
            yield cleaned


def split_aliases(raw: str, separator: str = ";") -> list[str]:
    """Split a delimited alias string into a list of non-empty alias strings.

    Args:
        raw: Alias string from a CSV cell (e.g. ``"Aspirin;ASA;Acetyl"``).
        separator: Field separator used between aliases. Defaults to ``";"``.

    Returns:
        A list of stripped alias strings; empty strings are excluded.
    """
    return [a.strip() for a in raw.split(separator) if a.strip()]
