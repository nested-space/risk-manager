"""Unit tests for the library selectable-table renderer."""

from typing import Any

import pytest

from riskmanager_cli.repl.renderers.library_renderer import (
    library_targets,
    render_library_screen,
)


def _item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "id-1",
        "name": "acetone",
        "display_name": "Acetone",
        "interpret_chemically": False,
        "smiles": "CC(=O)C",
        "alias_count": 0,
    }
    base.update(overrides)
    return base


@pytest.mark.unit
async def test_render_library_select_lists_subsections() -> None:
    """The 'select' sub-mode renders the subsection chooser, not a table."""
    lines = await render_library_screen("select", [])
    assert lines[0] == "Library"
    assert "  /library materials" in lines
    assert "  /library ncrm" in lines
    assert "  /library counterions" in lines


@pytest.mark.unit
async def test_render_library_empty_shows_placeholder() -> None:
    """A subsection with no items shows the no-items placeholder."""
    lines = await render_library_screen("materials", [])
    assert lines[0] == "Library · materials"
    assert "(no items found)" in lines


@pytest.mark.unit
async def test_render_library_table_has_column_headers() -> None:
    """The table renders the Name/Display name/Aliases/SMILES headers."""
    lines = await render_library_screen("materials", [_item()])
    header = next(line for line in lines if "Name" in line and "SMILES" in line)
    assert "Display name" in header
    assert "Aliases" in header


@pytest.mark.unit
async def test_render_library_caret_marks_selected_row() -> None:
    """The selected row carries a '> ' caret; others are indented."""
    items = [_item(id="a", name="acetone"), _item(id="b", name="butanol")]
    lines = await render_library_screen("materials", items, selected_id="b")
    caret_lines = [line for line in lines if line.startswith("> ")]
    assert len(caret_lines) == 1
    assert "butanol" in caret_lines[0]
    # The unselected data row keeps the two-space gutter.
    assert any(line.startswith("  ") and "acetone" in line for line in lines)


@pytest.mark.unit
async def test_render_library_chemically_renders_display_name() -> None:
    """interpret_chemically display names are subscripted in the table."""
    item = _item(name="sulfate", display_name="H2SO4", interpret_chemically=True)
    lines = await render_library_screen("counterions", [item])
    assert any("H₂SO₄" in line for line in lines)
    assert not any("H2SO4" in line for line in lines)


@pytest.mark.unit
async def test_render_library_shows_alias_count() -> None:
    """The alias count appears as its own cell."""
    lines = await render_library_screen("materials", [_item(alias_count=3)])
    assert any(" 3 " in line for line in lines)


@pytest.mark.unit
async def test_render_library_preserves_input_order() -> None:
    """Rows render in the order supplied (sorting happens upstream)."""
    items = [_item(id="a", name="alpha"), _item(id="z", name="zeta")]
    lines = await render_library_screen("materials", items)
    alpha_at = next(i for i, line in enumerate(lines) if "alpha" in line)
    zeta_at = next(i for i, line in enumerate(lines) if "zeta" in line)
    assert alpha_at < zeta_at


@pytest.mark.unit
def test_library_targets_label_and_id() -> None:
    """library_targets keys each item by id and labels it by name."""
    targets = library_targets([_item(id="x", name="xylene")])
    assert len(targets) == 1
    assert targets[0].item_id == "x"
    assert targets[0].label == "xylene"
