"""Overlay container (StackPane): composite blocks onto one fixed region.

Unlike :func:`~.stacks.vstack` / :func:`~.stacks.hstack`, which flow blocks
relative to one another, the overlay paints several blocks onto a single
``width × height`` canvas, each anchored to a corner or the centre by its own
``(HAlign, VAlign)``. It is the "A top-left, B bottom-right, C centre" pane: a way
to place independent elements within one bounded area.

Placements are painted in order, so a later placement wins over an earlier one
where they overlap (resolved at whole-segment granularity — a styled run is never
split mid-escape). The common corner/centre placements do not overlap, so the
result is exact; the container pads with spaces but does not clip, so a block
wider than the canvas is the caller's responsibility to size.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Block, HAlign, VAlign, block_width, visible_len


@dataclass(frozen=True)
class Placement:
    """One block to paint onto an :func:`overlay` canvas at a 2-D anchor.

    Attributes:
        block: The lines to paint (may carry ANSI escapes).
        halign: Horizontal anchor of the block within the canvas width.
        valign: Vertical anchor of the block within the canvas height.
    """

    block: Block
    halign: HAlign = "left"
    valign: VAlign = "top"


# Per row, a painted span as (start_col, end_col, segment); end is exclusive.
_Span = tuple[int, int, str]


def _origin(span: int, extent: int, align: str) -> int:
    """Return the start offset placing a *span*-long block in *extent* by *align*."""
    if align in ("right", "bottom"):
        return max(extent - span, 0)
    if align in ("center", "middle"):
        return max((extent - span) // 2, 0)
    return 0


def _paint(rows: list[list[_Span]], placement: Placement, width: int, height: int) -> None:
    """Splice *placement*'s lines into *rows*, dropping any spans they overlap."""
    col0 = _origin(block_width(placement.block), width, placement.halign)
    row0 = _origin(len(placement.block), height, placement.valign)
    for offset, line in enumerate(placement.block):
        row = row0 + offset
        span = visible_len(line)
        if not 0 <= row < height or span == 0:
            continue
        start, end = col0, col0 + span
        kept = [existing for existing in rows[row] if existing[1] <= start or existing[0] >= end]
        kept.append((start, end, line))
        rows[row] = kept


def _compose_row(painted: list[_Span], width: int) -> str:
    """Assemble one canvas row from its painted spans, space-filling the gaps."""
    cursor = 0
    parts: list[str] = []
    for start, end, segment in sorted(painted, key=lambda span: span[0]):
        if start > cursor:
            parts.append(" " * (start - cursor))
        parts.append(segment)
        cursor = end
    if cursor < width:
        parts.append(" " * (width - cursor))
    return "".join(parts)


def overlay(width: int, height: int, placements: list[Placement]) -> Block:
    """Paint *placements* onto a *width* × *height* canvas of spaces.

    Each placement's block is anchored as a unit by its ``(halign, valign)``;
    its lines are spliced into the canvas rows at the resulting column. Later
    placements override earlier ones in any row segment they overlap.

    Args:
        width: Canvas width in visible columns.
        height: Canvas height in rows.
        placements: Blocks to composite, painted in order (last wins on overlap).

    Returns:
        Exactly *height* rows. Each row is at least *width* columns wide (wider
        only if a placement block overruns the canvas, which is not clipped).
    """
    rows: list[list[_Span]] = [[] for _ in range(max(height, 0))]
    for placement in placements:
        _paint(rows, placement, width, height)
    return [_compose_row(painted, width) for painted in rows]
