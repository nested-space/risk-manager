"""Unit tests for the reusable unicode box widget."""

import pytest

from riskmanager_cli.repl.renderers.layout import render_box


@pytest.mark.unit
def test_render_box_lines_share_one_width() -> None:
    """Every box line is exactly *width* columns wide."""
    lines = render_box(["abc", "de"], 20, pad_x=2, pad_y=1)
    assert {len(line) for line in lines} == {20}


@pytest.mark.unit
def test_render_box_has_corners_and_borders() -> None:
    """Top/bottom rows are framed corners; interior rows carry side borders."""
    lines = render_box(["x"], 12, pad_x=1, pad_y=1)
    assert lines[0].startswith("┌") and lines[0].endswith("┐")
    assert lines[-1].startswith("└") and lines[-1].endswith("┘")
    assert all(line.startswith("│") and line.endswith("│") for line in lines[1:-1])


@pytest.mark.unit
def test_render_box_pads_y_rows_top_and_bottom() -> None:
    """``pad_y`` blank interior rows wrap the content on both sides."""
    lines = render_box(["content"], 30, pad_x=2, pad_y=2)
    # top border + 2 blank + 1 content + 2 blank + bottom border
    assert len(lines) == 1 + 2 + 1 + 2 + 1
    assert lines[1].strip("│ ") == ""  # first interior row is blank
    assert "content" in lines[3]  # content sits after the pad_y rows


@pytest.mark.unit
def test_render_box_centers_block_uniformly() -> None:
    """Centering shifts the whole block by one margin, preserving art alignment."""
    lines = render_box(["##", "#"], 20, pad_x=2, pad_y=0, align="center")
    content = [line for line in lines if "#" in line]
    # Both rows start their content at the same column (uniform left margin).
    assert content[0].index("#") == content[1].index("#")


@pytest.mark.unit
def test_render_box_left_align_flushes_to_padding() -> None:
    """Left alignment places content right after the ``pad_x`` gutter."""
    lines = render_box(["hi"], 20, pad_x=3, pad_y=0, align="left")
    row = next(line for line in lines if "hi" in line)
    assert row == "│" + " " * 3 + "hi" + " " * (20 - 2 - 3 - 2) + "│"


@pytest.mark.unit
def test_render_box_measures_visible_width_of_styled_lines() -> None:
    """ANSI escape sequences do not count toward width when padding/centering."""
    styled = "\x1b[2mlabel\x1b[0m"  # visible width 5
    plain = "label"
    styled_box = render_box([styled], 24, pad_x=2, pad_y=0)
    plain_box = render_box([plain], 24, pad_x=2, pad_y=0)
    # The styled line is longer in bytes but the box still measures 24 columns…
    content_row = next(line for line in styled_box if "label" in line)
    assert len(content_row) > 24  # escapes inflate the raw length
    # …and the printable layout matches the unstyled equivalent once stripped.
    import re

    stripped = re.sub(r"\x1b\[[0-9;]*m", "", content_row)
    assert stripped == next(line for line in plain_box if "label" in line)


@pytest.mark.unit
def test_render_box_empty_content_yields_a_hollow_box() -> None:
    """Empty content still frames a single blank interior row."""
    lines = render_box([], 10, pad_x=1, pad_y=0)
    assert len(lines) == 3  # top, one blank interior, bottom
    assert {len(line) for line in lines} == {10}
