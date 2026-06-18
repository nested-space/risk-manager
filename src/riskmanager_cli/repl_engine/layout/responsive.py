"""Pure layout primitives for responsive terminal rendering.

These helpers decide *how much room each element gets* for a given terminal
width, independent of what is drawn. They are shared by the table renderer
(:mod:`tables`) and the landing screen (:mod:`home_renderer`) so every screen
adapts to a resize through one consistent set of rules:

* :func:`fit_widths` shrinks a row of columns proportionally to their slack.
* :func:`select_columns` hides the least-important columns when even their
  minimum widths cannot all fit.
* :func:`lay_out_row` shrinks a row of equal-width cards toward a floor, then
  signals a vertical stack once they can no longer sit side by side.
* :func:`widest_fitting` picks the largest of several pre-rendered variants
  (e.g. banner sizes) that fits the available width.

All functions are deterministic and presentation-only; they take and return
plain numbers and text, never touching a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass


def fit_widths(natural: list[int], minimums: list[int], budget: int) -> list[int]:
    """Shrink *natural* column widths so their sum fits *budget*.

    Reduction is shared across columns in proportion to each column's slack
    (``natural - floor``), so wide columns give up room before narrow ones reach
    their floor.

    Args:
        natural: Each column's content-sized width.
        minimums: Each column's preferred floor.
        budget: Total content columns available (table width minus borders and
            padding).

    Returns:
        The fitted per-column widths, summing to at most ``budget`` whenever that
        is achievable without collapsing a column below its floor.

    Why this exists:
        When every minimum cannot be honoured (``sum(minimums) > budget``) the
        floors are dropped to a single column each, so the table shrinks evenly
        rather than letting one fragile column be erased.
    """
    if sum(natural) <= budget:
        return list(natural)
    floors = [min(m, n) for m, n in zip(minimums, natural, strict=True)]
    if sum(floors) > budget:
        floors = [min(1, n) for n in natural]
    slack = [n - f for n, f in zip(natural, floors, strict=True)]
    total_slack = sum(slack)
    if total_slack <= 0:
        return floors
    excess = sum(natural) - budget
    widths = list(natural)
    removed = 0
    for index, give in enumerate(slack):
        take = give * excess // total_slack
        widths[index] -= take
        removed += take
    # Largest-remainder rounding can leave a few columns over budget; trim the
    # shortfall from any column that still sits above its floor.
    index = 0
    while removed < excess:
        if widths[index] > floors[index]:
            widths[index] -= 1
            removed += 1
        index = (index + 1) % len(widths)
    return widths


def select_columns(
    min_widths: list[int],
    priorities: list[int | None],
    max_width: int,
    *,
    per_column_overhead: int = 3,
    fixed_overhead: int = 1,
) -> list[int]:
    """Return the indices of columns to keep so the kept set fits *max_width*.

    Columns whose *priority* is ``None`` are never dropped. Among droppable
    columns (priority set), the lowest priority is removed first; ties are
    broken by dropping the rightmost column. Dropping stops as soon as the kept
    columns' minimum widths plus their box overhead fit *max_width*, or once no
    droppable column remains.

    Args:
        min_widths: Each column's minimum content width.
        priorities: Per-column drop priority; ``None`` pins a column in place,
            and a lower integer is dropped before a higher one.
        max_width: Total columns the rendered row (content plus overhead) may
            occupy.
        per_column_overhead: Non-content columns each column costs (borders and
            padding). Defaults to a box table's ``│`` plus two pad spaces.
        fixed_overhead: Non-content columns the row costs regardless of column
            count (the closing ``│``).

    Returns:
        The kept column indices in ascending order; never empty.

    Why this exists:
        Proportional shrinking alone collapses a wide table into unreadable
        slivers on a narrow terminal. Hiding the least-important columns keeps
        the survivors legible instead.
    """
    kept = list(range(len(min_widths)))

    def fits(indices: list[int]) -> bool:
        content = sum(min_widths[i] for i in indices)
        overhead = per_column_overhead * len(indices) + fixed_overhead
        return content + overhead <= max_width

    def drop_order(index: int) -> tuple[int, int]:
        """Sort key: lowest priority first, then rightmost (largest index)."""
        priority = priorities[index]
        return (priority if priority is not None else 0, -index)

    while len(kept) > 1 and not fits(kept):
        droppable = [i for i in kept if priorities[i] is not None]
        if not droppable:
            break
        kept.remove(min(droppable, key=drop_order))
    return kept


@dataclass(frozen=True)
class RowPlan:
    """How a row of equal-width items should be laid out for a terminal width.

    Attributes:
        stacked: When ``True`` the items cannot sit side by side and the caller
            should stack them vertically instead.
        item_width: Width to render each item at, whether stacked or in a row.
    """

    stacked: bool
    item_width: int


def lay_out_row(count: int, *, item_min: int, item_ideal: int, gap: int, available: int) -> RowPlan:
    """Plan a row of *count* equal-width items within *available* columns.

    Items render at *item_ideal* when the full row fits, otherwise shrink toward
    *item_min*. Once even *item_min* items plus their gaps overflow *available*,
    the plan switches to a vertical stack, where each item keeps a legible width
    of at least *item_min* (clamped to *item_ideal*) even if *available* is
    smaller — the caller's draw layer clips the overflow rather than rendering a
    sliver.

    Args:
        count: Number of items in the row.
        item_min: Narrowest acceptable item width before stacking.
        item_ideal: Preferred item width when there is room.
        gap: Blank columns between adjacent items in row layout.
        available: Total columns available for the row.

    Returns:
        A :class:`RowPlan` describing the layout mode and per-item width.
    """
    if count <= 0:
        return RowPlan(stacked=False, item_width=item_ideal)
    gaps = gap * (count - 1)
    if count * item_ideal + gaps <= available:
        return RowPlan(stacked=False, item_width=item_ideal)
    if count * item_min + gaps <= available:
        width = max(item_min, min(item_ideal, (available - gaps) // count))
        return RowPlan(stacked=False, item_width=width)
    return RowPlan(stacked=True, item_width=max(item_min, min(item_ideal, available)))


def widest_fitting(variants: list[list[str]], width: int) -> list[str]:
    """Return the first of *variants* whose block width fits *width*.

    Args:
        variants: Candidate text blocks ordered widest first; each block is a
            list of plain (un-styled) lines.
        width: Available terminal columns.

    Returns:
        The widest variant that fits, or the narrowest variant when none fit.
        An empty *variants* list yields an empty block.
    """
    if not variants:
        return []
    for variant in variants:
        if max((len(line) for line in variant), default=0) <= width:
            return variant
    return variants[-1]
