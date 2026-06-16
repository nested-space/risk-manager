"""Box-drawn tab container: labelled tabs above a framed content body.

The TabPane draws a literal ``┌─┬─┐`` strip of tab labels whose *active* tab opens
down into a framed body, while the inactive tabs sit on the body's top border:

```
┌───────────┬─────────────┐
│ Libraries │ Information │
├───────────┘             └─────────────────────────┐
│ body …                                            │
└───────────────────────────────────────────────────┘
```

Switching tabs is the caller's concern (a key handler updates *active* and
re-renders); this module only draws a given active index. It is presentation-only
and terminal-agnostic — styling for the active label is supplied as *emphasize*.
"""

from __future__ import annotations

from collections.abc import Callable

from .geometry import Block, pad_block, pad_line, visible_len


def _label_row(tabs: list[str], active: int, total: int, emphasize: Callable[[str], str]) -> str:
    """Build the ``│ Tab │ … │`` label row, styling the active label cell."""
    cells = [
        emphasize(f" {label} ") if index == active else f" {label} "
        for index, label in enumerate(tabs)
    ]
    return pad_line("│" + "│".join(cells) + "│", total)


def _connector_row(segments: list[int], active: int, total: int, strip: int) -> str:
    """Build the row joining the tabs to the body, opening the *active* tab.

    The active tab's underline is a space notch; its boundaries turn into the
    body (``┘`` on the left, ``└`` on the right), while inactive tabs keep a drawn
    ``─`` underline. Past the tab strip the body's top border runs to the ``┐``.
    """
    count = len(segments)
    parts = ["├" if active != 0 else "│"]
    for index in range(count):
        parts.append((" " if index == active else "─") * segments[index])
        if index == count - 1:
            parts.append("└" if index == active else "┴")
        elif index + 1 == active:
            parts.append("┘")  # border meets the open tab's left wall
        elif index == active:
            parts.append("└")  # open tab's right wall, border resumes
        else:
            parts.append("┴")
    core = "".join(parts)  # exactly ``strip`` columns, ending in the last boundary
    if total > strip:
        return core + "─" * (total - strip - 1) + "┐"
    return core[:-1] + "┐"  # the tab strip fills the width: last boundary is the corner


def tabpane(
    tabs: list[str], active: int, body: Block, *, width: int, emphasize: Callable[[str], str] = str
) -> Block:
    """Render *tabs* above a framed *body*, with *active* opened into the body.

    Args:
        tabs: Tab labels, left to right (at least one).
        active: Index of the open tab; its underline is a notch into the body and
            its label is run through *emphasize*.
        body: Content lines shown in the framed area below the tabs. Pad the body
            beforehand (e.g. with :func:`~.geometry.pad_block`) for a fixed height.
        width: Total visible width of the pane; the body spans it, and the tab
            strip sits at the top-left (never wider than the pane).
        emphasize: Styler applied to the active tab's label cell.

    Returns:
        The pane's display lines, each exactly ``max(width, tab-strip width)``
        columns wide.
    """
    segments = [visible_len(label) + 2 for label in tabs]  # one space each side
    strip = sum(segments) + len(tabs) + 1  # tab cells plus their │ separators
    total = max(width, strip)
    inner = max(total - 2, 0)

    top = pad_line("┌" + "┬".join("─" * seg for seg in segments) + "┐", total)
    labels = _label_row(tabs, active, total, emphasize)
    connector = _connector_row(segments, active, total, strip)
    body_lines = [f"│{line}│" for line in pad_block(body, inner, len(body))]
    bottom = "└" + "─" * inner + "┘"

    return [top, labels, connector, *body_lines, bottom]
