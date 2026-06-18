"""Geometry foundation for the layout engine: width measurement and 2-D padding.

This is the lowest layer of the layout package: it owns the single ANSI-aware
width measurement used everywhere (so containers, frames and tables all agree on
how wide a styled line is) and the alignment vocabulary the rest of the package
shares. Every higher layout module (:mod:`stacks`, :mod:`overlay`, :mod:`frame`,
:mod:`table`, :mod:`tabpane`) builds on these primitives rather than re-deriving
escape-stripping or centring maths.

A *block* (:data:`Block`) is simply a list of display lines that may carry ANSI
styling escapes; widths are always measured by *printable* columns so a styled
line aligns the same as a plain one.
"""

from __future__ import annotations

import re
from typing import Literal

#: Horizontal placement within a field.
HAlign = Literal["left", "center", "right"]

#: Vertical placement within a field.
VAlign = Literal["top", "middle", "bottom"]

#: A rendered block: display lines that may carry ANSI styling escapes.
Block = list[str]

# Matches CSI/SGR escape sequences (e.g. those emitted by ``Terminal.dim``) so
# every width measurement counts only printable columns. This is the sole owner
# of the pattern; nothing else in the package re-derives it.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(text: str) -> int:
    """Return the printable column width of *text*, ignoring ANSI escapes."""
    return len(_ANSI_RE.sub("", text))


def block_width(block: Block) -> int:
    """Return the widest visible line width in *block* (zero for an empty block)."""
    return max((visible_len(line) for line in block), default=0)


def pad_line(line: str, width: int, align: HAlign = "left") -> str:
    """Pad *line* with spaces to *width* visible columns, placed by *align*.

    Padding is added on the side(s) implied by *align* and measured by visible
    width, so a styled line ends up the same printable width as a plain one. A
    line already at least *width* columns wide is returned unchanged (this helper
    pads but never clips — truncation is the table layer's concern).

    Args:
        line: The text to pad (may carry ANSI escapes).
        width: Target visible width.
        align: Where the existing text sits within the padded field.

    Returns:
        The padded line.
    """
    deficit = width - visible_len(line)
    if deficit <= 0:
        return line
    if align == "right":
        return " " * deficit + line
    if align == "center":
        left = deficit // 2
        return " " * left + line + " " * (deficit - left)
    return line + " " * deficit


def pad_block(
    block: Block, width: int, height: int, *, halign: HAlign = "left", valign: VAlign = "top"
) -> Block:
    """Pad *block* to an exact *width* × *height* field of cells.

    Each existing line is padded horizontally to *width* by *halign*; blank rows
    are then added above and/or below by *valign* until the block is *height* rows
    tall. The result is a solid rectangle every container can composite, with
    visible widths honoured so styled content stays aligned. A block already at or
    beyond *width*/*height* is not clipped.

    Args:
        block: The lines to pad (may carry ANSI escapes).
        width: Target visible width of every row.
        height: Target number of rows.
        halign: Horizontal placement of each line within *width*.
        valign: Vertical placement of *block* within *height*.

    Returns:
        Exactly ``max(height, len(block))`` rows, each ``max(width, …)`` columns.
    """
    rows = [pad_line(line, width, halign) for line in block]
    blank = " " * max(width, 0)
    missing = max(height - len(rows), 0)
    if missing == 0:
        return rows
    if valign == "bottom":
        return [blank] * missing + rows
    if valign == "middle":
        top = missing // 2
        return [blank] * top + rows + [blank] * (missing - top)
    return rows + [blank] * missing
