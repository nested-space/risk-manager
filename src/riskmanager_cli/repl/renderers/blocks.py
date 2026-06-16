"""Pure text-block composition helpers shared across card-based screens.

These functions measure and arrange pre-rendered blocks of display lines
(centring them in a width, joining them side by side) while respecting ANSI
styling, so a block may carry escape sequences and still align by *printable*
width. They are presentation-only and terminal-agnostic — the landing screen
(:mod:`home_renderer`) and the library home (:mod:`library_home_renderer`) both
build their card layouts from them rather than duplicating the geometry.
"""

from __future__ import annotations

import re

from ..viewport import tag_selected

# Matches CSI/SGR escape sequences so block widths count only printable columns.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(text: str) -> int:
    """Return the printable column width of *text*, ignoring ANSI escapes."""
    return len(_ANSI_RE.sub("", text))


def block_width(lines: list[str]) -> int:
    """Return the widest visible line width in a block."""
    return max((visible_len(line) for line in lines), default=0)


def center_block(lines: list[str], width: int) -> list[str]:
    """Indent every line by a shared left margin so the block is centred in *width*."""
    margin = max((width - block_width(lines)) // 2, 0)
    pad = " " * margin
    return [f"{pad}{line}" for line in lines]


def join_horizontal(blocks: list[list[str]], gap: int) -> list[str]:
    """Concatenate equal-or-ragged box blocks side by side with a *gap* between them.

    Each block is padded to the tallest block's height and to its own widest
    visible line, so a uniform spacer keeps the columns aligned even when blocks
    carry ANSI styling.

    Args:
        blocks: One list of display lines per column.
        gap: Number of blank columns between adjacent blocks.

    Returns:
        The merged rows spanning all blocks.
    """
    height = max((len(block) for block in blocks), default=0)
    padded: list[list[str]] = []
    for block in blocks:
        width = block_width(block)
        rows = [*block, *([""] * (height - len(block)))]
        padded.append([line + " " * (width - visible_len(line)) for line in rows])
    spacer = " " * gap
    return [spacer.join(parts) for parts in zip(*padded)]


def card_row(
    boxes: list[list[str]], *, width: int, gap: int, selected_index: int, stacked: bool
) -> list[str]:
    """Lay pre-rendered card *boxes* in a centred row, or a vertical stack.

    The *selected_index* card (or its whole stacked block) is tagged as the
    selection via :func:`~..viewport.tag_selected` so the viewport keeps it on
    screen while the page scrolls. Whether the cards fit a row or must stack is
    decided by the caller (typically :func:`responsive.lay_out_row`) and passed
    in as *stacked*, since the same plan also sizes the boxes.

    Args:
        boxes: One framed card per column, already sized and styled.
        width: Width to centre the row or each stacked card within.
        gap: Blank columns between adjacent cards in row layout.
        selected_index: Index of the highlighted card; negative tags nothing.
        stacked: When ``True`` the cards are stacked vertically rather than
            placed side by side.

    Returns:
        The composed card lines, with the selection tagged.
    """
    if stacked:
        lines: list[str] = []
        for index, box in enumerate(boxes):
            if index:
                lines.append("")
            centred = center_block(box, width)
            lines.extend(tag_selected(centred) if index == selected_index else centred)
        return lines
    row = center_block(join_horizontal(boxes, gap), width)
    return tag_selected(row) if 0 <= selected_index < len(boxes) else row
