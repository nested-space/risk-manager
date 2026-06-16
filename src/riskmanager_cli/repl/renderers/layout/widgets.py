"""Content widgets: the small, repeated text shapes screens compose.

These build the headings, paragraphs and cards that every screen would otherwise
re-implement inline — an underlined :func:`title`, a section-rule :func:`subtitle`,
a wrapped :func:`text_area` (and :func:`bullet_list`), and a framed :func:`card`.
Each returns a :data:`~.geometry.Block` so they drop straight into the stacking
containers. They are presentation-only and terminal-agnostic.
"""

from __future__ import annotations

import textwrap

from .frame import render_box
from .geometry import Block, HAlign, visible_len
from .table import section_rule, section_width


def title(text: str) -> Block:
    """Return *text* underlined with a ``─`` rule of matching visible width."""
    return [text, "─" * visible_len(text)]


def subtitle(text: str, term_width: int) -> Block:
    """Return a one-line section heading sized to *term_width*.

    Wraps :func:`~.table.section_rule`/:func:`~.table.section_width` so screens
    get a consistent heading without importing the table module directly.
    """
    return [section_rule(text, section_width(term_width))]


def text_area(text: str, width: int) -> Block:
    """Return *text* wrapped to *width* columns as a paragraph block."""
    return textwrap.wrap(text, width=max(width, 1))


def bullet_list(items: list[str], width: int, *, marker: str = "• ") -> Block:
    """Return *items* as a wrapped bullet list with a hanging indent.

    Each item wraps to *width* columns; continuation lines align under the text
    so the *marker* stays alone in the left gutter.
    """
    indent = " " * len(marker)
    lines: Block = []
    for item in items:
        wrapped = textwrap.wrap(
            item, width=max(width, 1), initial_indent=marker, subsequent_indent=indent
        )
        lines.extend(wrapped or [f"{marker}{item}"])
    return lines


def card(
    heading: str,
    body: Block | None = None,
    *,
    width: int,
    align: HAlign = "center",
    pad_y: int = 1,
) -> Block:
    """Frame a *heading* over an optional *body* in a unicode box of *width*.

    Standardises the ``render_box([heading, "", *body])`` shape the landing
    screens repeat: the heading, a blank separator, then the body lines.

    Args:
        heading: Card title shown on the first content row.
        body: Lines shown below the heading (a blank row separates them); when
            ``None`` or empty the card holds only the heading.
        width: Total visible width of the framed box, including borders.
        align: Horizontal placement of the content block within the box.
        pad_y: Blank interior rows above and below the content.

    Returns:
        The framed card lines, each exactly *width* columns wide.
    """
    content = [heading, "", *body] if body else [heading]
    return render_box(content, width, align=align, pad_y=pad_y)
