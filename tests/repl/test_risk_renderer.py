"""Unit tests for the risk-mode table renderer."""

import pytest

from riskmanager_cli.repl.renderers.risk_renderer import render_risk_table


@pytest.mark.unit
async def test_render_risk_table_uses_box_table_with_severity_labels() -> None:
    """Risks render as a box-drawn table with ``Name (n)`` level cells."""
    risks = [
        {
            "risk_type": "Safety",
            "name": "Exotherm",
            "current_level": 5,
            "mitigated_level": 2,
            "scope": "Stage 1",
        }
    ]

    lines = await render_risk_table(risks, scope_label="stage · Stage 1")
    joined = "\n".join(lines)

    assert lines[0] == "Risks · stage · Stage 1"
    # Box-table borders and a header row from the shared renderer.
    assert any(line.startswith("┌") for line in lines)
    assert any(line.startswith("│") and "Level" in line for line in lines)
    # Levels are labelled with their severity and number; mitigated likewise.
    assert "VH (5)" in joined
    assert "L (2)" in joined


@pytest.mark.unit
async def test_render_risk_table_empty_state() -> None:
    """With no risks the renderer shows the title and an empty-state notice."""
    lines = await render_risk_table([], scope_label="stage · Stage 1")
    assert lines == ["Risks · stage · Stage 1", "", "(no risks recorded)"]


@pytest.mark.unit
async def test_render_risk_table_unset_level_renders_dash() -> None:
    """A missing level renders as ``-`` rather than crashing."""
    risks = [{"risk_type": "Quality", "name": "Carryover", "scope": "1.1"}]
    lines = await render_risk_table(risks, scope_label="route 1.1")
    assert any(" - " in line for line in lines)


@pytest.mark.unit
async def test_render_risk_table_wraps_long_name() -> None:
    """A long risk name wraps across lines instead of being clipped."""
    long_name = "Runaway heat during slow reagent addition then late quench step"
    risks = [
        {
            "risk_type": "Safety",
            "name": long_name,
            "current_level": 5,
            "mitigated_level": 2,
            "scope": "Stage 1",
        }
    ]

    lines = await render_risk_table(risks, scope_label="stage · Stage 1", width=60)

    # The data rows between the header separator and the bottom border span more
    # than one physical line: the Name column wrapped rather than being clipped.
    data = [line for line in lines if line.startswith("│") and "Level" not in line]
    assert len(data) > 1
    joined_words = "".join(data)
    for word in ("Runaway", "during", "reagent", "addition", "quench", "step"):
        assert word in joined_words
