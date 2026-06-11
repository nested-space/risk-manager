"""Reusable unicode box widget for framing a block of content.

Frames a block of pre-rendered lines in a ``┌─┐ │ └─┘`` box that spans a given
visible width, with configurable interior padding and block alignment. Unlike
``tables.py`` (which assumes plain text), this widget is ANSI-aware: content
lines may carry styling escape sequences (e.g. ``dim`` stage labels in the route
diagram), so width is measured by *printable* length when centering and padding.

The box is screen-agnostic — any screen can frame content the same way.
"""

from __future__ import annotations

import re

from .tables import Align

# Matches CSI/SGR escape sequences (e.g. those emitted by ``Terminal.dim``) so
# alignment and padding count only printable columns.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_TOP_LEFT, _TOP_RIGHT = "┌", "┐"
_BOTTOM_LEFT, _BOTTOM_RIGHT = "└", "┘"
_HORIZONTAL, _VERTICAL = "─", "│"


def _visible_len(text: str) -> int:
    """Return the printable column width of *text*, ignoring ANSI escapes."""
    return len(_ANSI_RE.sub("", text))


def render_box(
    content: list[str],
    width: int,
    *,
    align: Align = "center",
    pad_x: int = 2,
    pad_y: int = 1,
) -> list[str]:
    """Frame *content* in a unicode box of total visible width *width*.

    Every returned line has the same visible width (*width*): a top border, then
    *pad_y* blank interior rows, the aligned content, *pad_y* more blank rows,
    and a bottom border. The content area between the ``│`` borders is inset by
    *pad_x* columns on each side.

    Alignment is applied to the block as a whole, not per line: the widest
    content line sets the block width and a single uniform left margin is applied
    to every line, so multi-line art (arrows, lanes) keeps its internal
    alignment. Lines may contain ANSI styling; their visible width is measured
    with :func:`_visible_len`.

    Args:
        content: Pre-rendered lines to frame (may be empty or styled).
        width: Total visible width of the box, including both borders.
        align: Horizontal placement of the content block within the interior.
        pad_x: Padding columns inside each vertical border.
        pad_y: Blank interior rows above and below the content.

    Returns:
        The box's display lines, each exactly *width* columns wide.
    """
    inner = max(width - 2, 0)
    field = max(inner - 2 * pad_x, 0)

    block_width = min(max((_visible_len(line) for line in content), default=0), field)
    if align == "right":
        left = field - block_width
    elif align == "center":
        left = (field - block_width) // 2
    else:
        left = 0

    def interior(cells: str) -> str:
        return f"{_VERTICAL}{' ' * pad_x}{cells}{' ' * pad_x}{_VERTICAL}"

    def content_row(line: str) -> str:
        pad = field - _visible_len(line)
        rendered = f"{' ' * left}{line}{' ' * (max(pad, 0) - left)}"
        return interior(rendered)

    blank = interior(" " * field)
    top = f"{_TOP_LEFT}{_HORIZONTAL * inner}{_TOP_RIGHT}"
    bottom = f"{_BOTTOM_LEFT}{_HORIZONTAL * inner}{_BOTTOM_RIGHT}"

    rows = [top, *([blank] * pad_y)]
    rows += [content_row(line) for line in content] if content else [blank]
    rows += [*([blank] * pad_y), bottom]
    return rows
