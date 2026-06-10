"""Unit tests for riskmanager_cli.utils.component_graph_layout."""

import pytest

from riskmanager_cli.utils.component_graph_layout import (
    ComponentInput,
    IncompleteProcessError,
    StageComponentInput,
    StageInput,
    render_component_graph,
    split_for_width,
)


def _components(*ids: str) -> list[ComponentInput]:
    return [ComponentInput(id=i, display_name=i) for i in ids]


def _stage(name: str, *links: tuple[str, str]) -> StageInput:
    return StageInput(
        name=name,
        stage_components=[StageComponentInput(component_id=c, component_type=t) for c, t in links],
    )


@pytest.mark.unit
def test_linear_chain_places_reactants_before_final_product() -> None:
    """A→B→C renders with A and B left of the final product C, all connected."""
    stages = [
        _stage("Stage 1", ("A", "reactant"), ("B", "product")),
        _stage("Stage 2", ("B", "reactant"), ("C", "product")),
    ]
    lines = render_component_graph(stages, _components("A", "B", "C"))

    joined = "\n".join(lines)
    assert "A" in joined and "B" in joined and "C" in joined
    # Columns increase left-to-right toward the final product.
    row = next(line for line in lines if "A" in line)
    assert row.index("A") < row.index("B") < row.index("C")
    # One arrow per stage.
    assert joined.count("▶") == 2


@pytest.mark.unit
def test_convergent_stage_aligns_reactant_column_and_bus() -> None:
    """A+B→C places both reactants in one column with a single aligned bus."""
    stages = [_stage("Stage 1", ("A", "reactant"), ("B", "reactant"), ("C", "product"))]
    lines = render_component_graph(stages, _components("A", "B", "C"))

    row_a = next(line for line in lines if "A" in line)
    row_b = next(line for line in lines if "B" in line)
    # Same distance from the final product ⇒ same column offset.
    assert row_a.index("A") == row_b.index("B")
    # The convergence bus is one straight vertical line: the top/bottom corners
    # sit in the same character column.
    assert "┐" in row_a and "┘" in row_b
    assert row_a.index("┐") == row_b.index("┘")
    # The stage label and product live on the junction row.
    junction = next(line for line in lines if "Stage 1" in line)
    assert "├" in junction and "▶" in junction and junction.rstrip().endswith("C")


@pytest.mark.unit
def test_same_depth_components_share_a_column() -> None:
    """Two reactants of one stage at equal depth start at the same offset."""
    stages = [
        _stage("S1", ("A", "reactant"), ("B", "reactant"), ("C", "product")),
        _stage("S2", ("C", "reactant"), ("D", "reactant"), ("E", "product")),
    ]
    lines = render_component_graph(stages, _components("A", "B", "C", "D", "E"))
    # C and D are both one step from the final product E ⇒ same column offset.
    # (Stage names are S1/S2, so C and D each appear on exactly one line.)
    row_c = next(line for line in lines if "C" in line)
    row_d = next(line for line in lines if "D" in line)
    assert row_c.index("C") == row_d.index("D")


@pytest.mark.unit
def test_non_isolated_component_is_bracketed() -> None:
    """A component with is_isolated=False renders wrapped in [brackets]."""
    stages = [_stage("Stage 1", ("A", "reactant"), ("C", "product"))]
    components = [
        ComponentInput(id="A", display_name="A"),
        ComponentInput(id="C", display_name="C", is_isolated=False),
    ]
    joined = "\n".join(render_component_graph(stages, components))
    assert "[C]" in joined
    # The isolated reactant is not bracketed.
    assert "[A]" not in joined


@pytest.mark.unit
def test_dim_wraps_stage_labels_only() -> None:
    """The dim callable styles stage labels but not component names."""
    stages = [_stage("Stage 1", ("A", "reactant"), ("B", "product"))]
    joined = "\n".join(
        render_component_graph(stages, _components("A", "B"), dim=lambda s: f"<{s}>")
    )
    assert "<Stage 1>" in joined
    assert "<A>" not in joined and "<B>" not in joined


@pytest.mark.unit
def test_split_returns_single_unheaded_section_when_it_fits() -> None:
    """A graph within max_width renders as one section with no title."""
    stages = [
        _stage("Stage 1", ("A", "reactant"), ("B", "product")),
        _stage("Stage 2", ("B", "reactant"), ("C", "product")),
    ]
    sections = split_for_width(stages, _components("A", "B", "C"), max_width=200)
    assert len(sections) == 1
    title, _lines = sections[0]
    assert title is None


@pytest.mark.unit
def test_split_breaks_wide_graph_into_route_sections() -> None:
    """A graph wider than max_width splits into titled, re-seeded sub-graphs."""
    stages = [
        _stage("Stage 1", ("A", "reactant"), ("B", "reactant"), ("C", "product")),
        _stage("Stage 2", ("C", "reactant"), ("D", "reactant"), ("E", "product")),
        _stage("Stage 3", ("E", "reactant"), ("F", "reactant"), ("G", "product")),
    ]
    sections = split_for_width(stages, _components("A", "B", "C", "D", "E", "F", "G"), max_width=40)
    assert len(sections) > 1
    titles = [title for title, _ in sections]
    assert all(title is not None and title.startswith("Route To ") for title in titles)
    # The final section routes to the overall final product.
    assert titles[-1] == "Route To G:"
    # The cut component re-appears as a seed reactant in the next section.
    assert any("C" in "\n".join(lines) for _title, lines in sections[1:])


@pytest.mark.unit
def test_no_stages_raises_incomplete() -> None:
    """An empty process cannot be laid out as a DAG."""
    with pytest.raises(IncompleteProcessError):
        render_component_graph([], [])


@pytest.mark.unit
def test_two_terminal_products_raises_incomplete() -> None:
    """Two disconnected transformations have two finals — not a single DAG."""
    stages = [
        _stage("S1", ("A", "reactant"), ("B", "product")),
        _stage("S2", ("C", "reactant"), ("D", "product")),
    ]
    with pytest.raises(IncompleteProcessError):
        render_component_graph(stages, _components("A", "B", "C", "D"))


@pytest.mark.unit
def test_multi_product_stage_raises_incomplete() -> None:
    """A stage with two products is invalid."""
    stages = [_stage("S1", ("A", "reactant"), ("B", "product"), ("C", "product"))]
    with pytest.raises(IncompleteProcessError):
        render_component_graph(stages, _components("A", "B", "C"))


@pytest.mark.unit
def test_cycle_raises_incomplete() -> None:
    """A→B and B→A form a cycle with no single terminal product."""
    stages = [
        _stage("S1", ("A", "reactant"), ("B", "product")),
        _stage("S2", ("B", "reactant"), ("A", "product")),
    ]
    with pytest.raises(IncompleteProcessError):
        render_component_graph(stages, _components("A", "B"))
