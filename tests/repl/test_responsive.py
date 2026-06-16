"""Unit tests for the pure responsive-layout primitives."""

import pytest

from riskmanager_cli.repl.renderers.responsive import (
    RowPlan,
    fit_widths,
    lay_out_row,
    select_columns,
    widest_fitting,
)


@pytest.mark.unit
def test_fit_widths_keeps_natural_when_within_budget() -> None:
    """Columns that already fit the budget are returned untouched."""
    assert fit_widths([5, 8], [4, 4], budget=20) == [5, 8]


@pytest.mark.unit
def test_fit_widths_shrinks_wide_column_before_narrow_reaches_floor() -> None:
    """Slack is surrendered proportionally, sparing the column near its floor."""
    widths = fit_widths([30, 6], [4, 4], budget=20)
    assert sum(widths) == 20
    assert widths[1] >= 4  # the narrow column keeps its floor


@pytest.mark.unit
def test_fit_widths_drops_floors_when_minimums_cannot_all_fit() -> None:
    """When even the floors overflow, no column collapses below one column."""
    widths = fit_widths([20, 20], [10, 10], budget=15)
    assert min(widths) >= 1
    assert sum(widths) <= 15


@pytest.mark.unit
def test_select_columns_keeps_all_when_minimums_fit() -> None:
    """An ample width keeps every column."""
    assert select_columns([8, 8, 8], [0, 1, None], max_width=80) == [0, 1, 2]


@pytest.mark.unit
def test_select_columns_drops_lowest_priority_first() -> None:
    """The least-important droppable column is hidden before others."""
    # min widths 10 each, overhead 3*n+1: three columns need 37, two need 26.
    kept = select_columns([10, 10, 10], [2, 0, 1], max_width=30)
    assert kept == [0, 2]  # priority-0 column (index 1) dropped


@pytest.mark.unit
def test_select_columns_breaks_ties_by_dropping_rightmost() -> None:
    """Equal-priority columns drop the rightmost one first."""
    kept = select_columns([10, 10, 10], [0, 0, 0], max_width=30)
    assert kept == [0, 1]


@pytest.mark.unit
def test_select_columns_never_drops_pinned_columns() -> None:
    """``None`` priorities are pinned even when the table cannot fit them."""
    kept = select_columns([10, 10], [None, None], max_width=5)
    assert kept == [0, 1]


@pytest.mark.unit
def test_select_columns_keeps_at_least_one_column() -> None:
    """Dropping stops at a single column even under extreme pressure."""
    kept = select_columns([10, 10, 10], [0, 1, 2], max_width=5)
    assert len(kept) == 1
    assert kept == [2]  # the highest-priority column survives


@pytest.mark.unit
def test_lay_out_row_uses_ideal_width_when_row_fits() -> None:
    """A wide terminal renders items at their ideal width, side by side."""
    plan = lay_out_row(3, item_min=19, item_ideal=28, gap=4, available=92)
    assert plan == RowPlan(stacked=False, item_width=28)


@pytest.mark.unit
def test_lay_out_row_shrinks_between_breakpoints() -> None:
    """Between the ideal and stacking widths, items shrink within their bounds."""
    plan = lay_out_row(3, item_min=19, item_ideal=28, gap=4, available=75)
    assert not plan.stacked
    assert 19 <= plan.item_width <= 28
    assert plan.item_width == (75 - 8) // 3


@pytest.mark.unit
def test_lay_out_row_stacks_below_minimum_row_width() -> None:
    """Once the minimum row no longer fits, the plan switches to a stack."""
    plan = lay_out_row(3, item_min=19, item_ideal=28, gap=4, available=60)
    assert plan.stacked is True
    assert plan.item_width == 28  # full width available when stacked


@pytest.mark.unit
def test_widest_fitting_picks_largest_variant_that_fits() -> None:
    """The first (widest) variant within the width is chosen."""
    wide = ["#" * 40]
    mid = ["#" * 20]
    narrow = ["#" * 5]
    assert widest_fitting([wide, mid, narrow], 25) is mid


@pytest.mark.unit
def test_widest_fitting_falls_back_to_narrowest() -> None:
    """When nothing fits, the narrowest (last) variant is returned."""
    wide = ["#" * 40]
    narrow = ["#" * 30]
    assert widest_fitting([wide, narrow], 10) is narrow
