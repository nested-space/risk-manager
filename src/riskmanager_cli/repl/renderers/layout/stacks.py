"""Vertical and horizontal stacking containers for composing blocks.

These containers arrange pre-rendered blocks relative to one another — one above
the next (:func:`vstack`) or side by side (:func:`hstack`) — measuring by visible
width so styled children stay aligned. They generalise the earlier ad-hoc
``lines += [...]`` concatenation and the top-aligning ``join_horizontal`` into one
consistent set of primitives, and carry the selection-aware :func:`card_row` used
by the landing screens. They are presentation-only and terminal-agnostic.
"""

from __future__ import annotations

from ...viewport import tag_selected
from .geometry import Block, HAlign, VAlign, block_width, pad_block


def _indent_block(block: Block, width: int, align: HAlign) -> Block:
    """Shift *block* within *width* by a single shared margin, preserving its shape.

    Alignment is applied to the block as a whole, not per line, so multi-line art
    (banners, arrows) keeps its internal alignment. Only a left margin is added;
    lines are not right-padded.
    """
    margin = width - block_width(block)
    if align == "right":
        margin = max(margin, 0)
    elif align == "center":
        margin = max(margin // 2, 0)
    else:
        margin = 0
    pad = " " * margin
    return [f"{pad}{line}" for line in block]


def center_block(lines: Block, width: int) -> Block:
    """Indent *lines* by a shared left margin so the block is centred in *width*."""
    return _indent_block(lines, width, "center")


def vstack(
    blocks: list[Block], *, gap: int = 0, align: HAlign = "left", width: int | None = None
) -> Block:
    """Stack *blocks* vertically, *gap* blank rows apart, aligned within a width.

    Each child block is shifted as a unit (see :func:`_indent_block`) to *align*
    it horizontally within *width* — the widest child when *width* is ``None`` —
    so internal multi-line structure is preserved.

    Args:
        blocks: Child blocks in top-to-bottom order.
        gap: Blank rows inserted between adjacent children.
        align: Horizontal placement of each child within the common width.
        width: Field width to align within; defaults to the widest child.

    Returns:
        The stacked lines.
    """
    target = width if width is not None else max((block_width(b) for b in blocks), default=0)
    out: Block = []
    for index, block in enumerate(blocks):
        if index and gap:
            out.extend([""] * gap)
        out.extend(_indent_block(block, target, align))
    return out


def hstack(blocks: list[Block], *, gap: int = 0, align: VAlign = "top") -> Block:
    """Place *blocks* side by side with a *gap* between, aligned vertically.

    Each child is padded to its own visible width and to the tallest child's
    height (placed by *align*), so a uniform spacer keeps the columns aligned even
    when children differ in height or carry ANSI styling.

    Args:
        blocks: Child blocks in left-to-right order.
        gap: Blank columns between adjacent children.
        align: Vertical placement of shorter children within the row height.

    Returns:
        The merged rows spanning all children.
    """
    if not blocks:
        return []
    height = max(len(block) for block in blocks)
    spacer = " " * gap
    padded = [pad_block(block, block_width(block), height, valign=align) for block in blocks]
    return [spacer.join(parts) for parts in zip(*padded, strict=True)]


def join_horizontal(blocks: list[Block], gap: int) -> Block:
    """Concatenate top-aligned blocks side by side with a *gap* between them.

    Thin wrapper over :func:`hstack` preserving the historical top-aligned
    behaviour for callers that only need a simple row.
    """
    return hstack(blocks, gap=gap, align="top")


def card_row(
    boxes: list[Block], *, width: int, gap: int, selected_index: int, stacked: bool
) -> Block:
    """Lay pre-rendered card *boxes* in a centred row, or a vertical stack.

    The *selected_index* card (or its whole stacked block) is tagged as the
    selection via :func:`~...viewport.tag_selected` so the viewport keeps it on
    screen while the page scrolls. Whether the cards fit a row or must stack is
    decided by the caller (typically :func:`responsive.lay_out_row`) and passed in
    as *stacked*, since the same plan also sizes the boxes.

    Args:
        boxes: One framed card per column, already sized and styled.
        width: Width to centre the row or each stacked card within.
        gap: Blank columns between adjacent cards in row layout.
        selected_index: Index of the highlighted card; negative tags nothing.
        stacked: When ``True`` the cards are stacked vertically rather than placed
            side by side.

    Returns:
        The composed card lines, with the selection tagged.
    """
    if stacked:
        lines: Block = []
        for index, box in enumerate(boxes):
            if index:
                lines.append("")
            centred = center_block(box, width)
            lines.extend(tag_selected(centred) if index == selected_index else centred)
        return lines
    row = center_block(join_horizontal(boxes, gap), width)
    return tag_selected(row) if 0 <= selected_index < len(boxes) else row
