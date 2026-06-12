"""Unit tests for the reusable table/section rendering primitives."""

import pytest

from riskmanager_cli.repl.renderers.tables import Column, render_table, section_rule


@pytest.mark.unit
def test_section_rule_fills_to_width() -> None:
    """The rule spans exactly *width* columns, trailing with ``─``."""
    rule = section_rule("Components", 30)
    assert rule.startswith("─ Components ")
    assert len(rule) == 30
    assert rule.endswith("─")


@pytest.mark.unit
def test_section_rule_never_shorter_than_prefix() -> None:
    """A narrow width still yields the full ``─ {title} `` prefix."""
    rule = section_rule("Risks", 2)
    assert rule == "─ Risks "


@pytest.mark.unit
def test_render_table_sizes_columns_to_widest_cell() -> None:
    """Each column widens to fit the longest of its header and cells."""
    lines = render_table([Column("Name"), Column("Role")], [["Acetonitrile", "Solvent"]])
    # Every line shares one visible width.
    assert len({len(line) for line in lines}) == 1
    # The data cell drives the first column's width, not the shorter header.
    assert "│ Acetonitrile │" in lines[3]


@pytest.mark.unit
def test_render_table_places_data_rows_after_three_header_lines() -> None:
    """Data rows occupy ``result[3 : 3 + len(rows)]`` between the borders."""
    rows = [["A", "Reactant"], ["B", "Product"]]
    lines = render_table([Column("Name"), Column("Role")], rows)
    assert lines[0].startswith("┌") and lines[0].endswith("┐")
    assert lines[2].startswith("├") and lines[2].endswith("┤")
    assert lines[-1].startswith("└") and lines[-1].endswith("┘")
    data = lines[3 : 3 + len(rows)]
    assert "A" in data[0] and "B" in data[1]


@pytest.mark.unit
def test_render_table_centers_aligned_columns() -> None:
    """A ``center`` column centres its cell while ``left`` left-justifies."""
    lines = render_table(
        [Column("Name"), Column("Level", align="center")],
        [["Equipment fault", "4"]],
    )
    # The single-character level sits centred in its column (spaces both sides).
    assert "│   4   │" in lines[3]
    # The name is left-justified flush after its leading pad space.
    assert lines[3].startswith("│ Equipment fault │")
