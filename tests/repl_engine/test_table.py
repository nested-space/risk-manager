"""Unit tests for the reusable table/section rendering primitives."""

import pytest

from riskmanager_cli.repl_engine.layout import (
    Column,
    render_table,
    render_table_blocks,
    section_rule,
)


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


def _column_widths(border: str) -> list[int]:
    """Recover each column's content width from a ``┌──┬──┐`` border line."""
    return [len(segment) - 2 for segment in border.strip("┌┐").split("┬")]


@pytest.mark.unit
def test_render_table_keeps_natural_width_when_budget_is_ample() -> None:
    """An ample *max_width* leaves the table identical to its natural rendering."""
    columns = [Column("Name"), Column("Role")]
    rows = [["Acetonitrile", "Solvent"]]
    assert render_table(columns, rows, max_width=200) == render_table(columns, rows)


@pytest.mark.unit
def test_render_table_shrinks_to_fit_and_elides_overflow() -> None:
    """An over-wide table is shrunk within budget and long cells gain ``…``."""
    lines = render_table(
        [Column("Name"), Column("SMILES")],
        [["Acetonitrile", "C1=CC=CC=C1OCC"]],
        max_width=20,
    )
    assert len({len(line) for line in lines}) == 1  # one shared width
    assert len(lines[0]) <= 20
    assert "…" in lines[3]  # at least one cell was clipped


@pytest.mark.unit
def test_render_table_respects_min_width_under_pressure() -> None:
    """A column is not shrunk below its ``min_width`` while another has slack."""
    lines = render_table(
        [Column("A"), Column("B", min_width=10)],
        [["x" * 30, "y" * 30]],
        max_width=21,
    )
    # Budget forces both to their floors: A to the default 4, B to its 10.
    assert _column_widths(lines[0]) == [4, 10]


@pytest.mark.unit
def test_render_table_drops_minimums_when_they_cannot_all_fit() -> None:
    """When the minimums exceed the budget, no column collapses below one column."""
    lines = render_table(
        [Column("A", min_width=10), Column("B", min_width=10)],
        [["x" * 20, "y" * 20]],
        max_width=15,
    )
    assert min(_column_widths(lines[0])) >= 1
    assert len(lines[0]) <= 15


@pytest.mark.unit
def test_render_table_hides_low_priority_column_when_too_narrow() -> None:
    """A droppable column is hidden so the pinned column stays legible."""
    columns = [Column("Name"), Column("Detail", priority=0)]
    rows = [["Acetonitrile", "long detail"], ["Water", "more detail"]]
    lines = render_table(columns, rows, max_width=12)
    # The pinned Name column survives; the priority-0 Detail column is gone.
    assert "Name" in lines[1]
    assert "Detail" not in lines[1]
    # Dropping a column changes content, not the row count.
    assert len(lines[3 : 3 + len(rows)]) == 2


@pytest.mark.unit
def test_render_table_keeps_pinned_columns_under_pressure() -> None:
    """Columns without a priority are never dropped, only shrunk."""
    columns = [Column("Name"), Column("Role")]
    lines = render_table(columns, [["Acetonitrile", "Solvent"]], max_width=12)
    assert len(_column_widths(lines[0])) == 2  # both columns kept, merely shrunk


@pytest.mark.unit
def test_render_table_blocks_reports_single_line_rows_without_wrapping() -> None:
    """With no wrap column, every row is one line and matches ``render_table``."""
    columns = [Column("Name"), Column("Role")]
    rows = [["A", "Reactant"], ["B", "Product"]]
    lines, spans = render_table_blocks(columns, rows)
    assert lines == render_table(columns, rows)
    assert spans == [1, 1]


@pytest.mark.unit
def test_render_table_wraps_a_wrap_column_across_lines() -> None:
    """A ``wrap=True`` column splits a long cell over several physical lines."""
    columns = [Column("Name"), Column("Note", wrap=True)]
    rows = [["A", "alpha beta gamma delta epsilon"]]
    lines, spans = render_table_blocks(columns, rows, max_width=22)
    # The row occupies more than one physical line and the span reports it.
    assert spans[0] > 1
    data = lines[3 : 3 + spans[0]]
    assert len(data) == spans[0]
    # No ellipsis: the text wrapped rather than being clipped.
    assert "…" not in "".join(data)
    # Every physical line shares the table's single width.
    assert len({len(line) for line in lines}) == 1
    # The wrapped words are all present across the row's lines.
    joined = "".join(data)
    for word in ("alpha", "beta", "gamma", "delta", "epsilon"):
        assert word in joined


@pytest.mark.unit
def test_render_table_clips_non_wrap_column_while_wrapping_another() -> None:
    """A non-wrap column is still clipped even when a sibling column wraps."""
    columns = [Column("Code", wrap=False), Column("Note", wrap=True)]
    rows = [["X" * 30, "alpha beta gamma delta"]]
    lines, _ = render_table_blocks(columns, rows, max_width=24)
    # The non-wrap Code column gains an ellipsis; only the Note column wraps.
    assert any("…" in line for line in lines[3:-1])


@pytest.mark.unit
def test_render_table_blocks_wraps_each_row_independently() -> None:
    """Per-row spans reflect each row's own height; short rows stay one line."""
    columns = [Column("Name"), Column("Note", wrap=True)]
    rows = [["A", "short"], ["B", "one two three four five six seven eight"]]
    _, spans = render_table_blocks(columns, rows, max_width=20)
    assert spans[0] == 1
    assert spans[1] > 1
