"""Selection-aware viewport model for the output pane.

The output pane renders a flat ``list[str]`` and scrolls by slicing it. Two
structural roles let any screen scroll intelligently rather than top-anchoring a
buffer that overflows the pane:

* **sticky** — a contiguous block at the very top that stays pinned while the
  rest scrolls under it (e.g. the landing banner, which must always be visible).
* **selected** — the line(s) the user has highlighted, kept on screen as they
  navigate (e.g. the focused home card, or a list/table row).

Renderers declare these by tagging lines with an invisible control prefix via
:func:`tag_sticky` / :func:`tag_selected`. :func:`parse` strips the tags and
returns the clean display lines plus the role ranges, so every other layer works
with ordinary text. This generalises the table-only header pinning in
:mod:`sticky_window` (which this module composes for the scrollable body) into
one model shared by tables, lists and the landing page alike.

Coordinates: ``offset`` is an index into the *scrollable body* — the lines below
the sticky region. For a screen with no sticky region the body is the whole
buffer, so the offset matches the historical whole-buffer offset exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sticky_window import pinned_window, reserved_top

# Invisible one-character line tags. Control characters never appear in rendered
# content, so a leading run of them unambiguously marks a line's role.
_STICKY = "\x01"
_SELECTED = "\x02"
_TAGS = (_STICKY, _SELECTED)


def tag_sticky(lines: list[str]) -> list[str]:
    """Mark *lines* as the pinned top region (kept visible while scrolling)."""
    return [_STICKY + line for line in lines]


def tag_selected(lines: list[str]) -> list[str]:
    """Mark *lines* as the current selection (kept on screen during navigation)."""
    return [_SELECTED + line for line in lines]


@dataclass(frozen=True)
class ViewModel:
    """A parsed output buffer: clean lines plus their structural roles.

    Attributes:
        lines: The display lines with all role tags stripped.
        sticky_count: Number of pinned lines at the top of :attr:`lines`.
        selected: Inclusive ``(start, end)`` line range of the selection, or
            ``None`` when nothing is tagged selected.
    """

    lines: list[str]
    sticky_count: int
    selected: tuple[int, int] | None


def parse(raw: list[str]) -> ViewModel:
    """Split *raw* into clean lines and the sticky/selected ranges they tag.

    Args:
        raw: Renderer output, possibly carrying :func:`tag_sticky` /
            :func:`tag_selected` prefixes.

    Returns:
        The :class:`ViewModel`. Untagged buffers yield ``sticky_count == 0`` and
        ``selected is None``, i.e. a plain scrollable buffer.
    """
    clean: list[str] = []
    sticky_flags: list[bool] = []
    selected_indices: list[int] = []
    for index, line in enumerate(raw):
        is_sticky = is_selected = False
        while line[:1] in _TAGS:
            is_sticky = is_sticky or line[0] == _STICKY
            is_selected = is_selected or line[0] == _SELECTED
            line = line[1:]
        clean.append(line)
        sticky_flags.append(is_sticky)
        if is_selected:
            selected_indices.append(index)

    sticky_count = 0
    for flagged in sticky_flags:
        if not flagged:
            break
        sticky_count += 1

    selected = (selected_indices[0], selected_indices[-1]) if selected_indices else None
    return ViewModel(lines=clean, sticky_count=sticky_count, selected=selected)


def selected_line(view: ViewModel) -> int | None:
    """Return a representative selected line index, or ``None``.

    Prefers an explicit :func:`tag_selected` range (its first line); otherwise
    falls back to a caret-marked row (``"▶ "``/``"> "``), the convention used by
    the list navigator and the selectable table screens.

    Args:
        view: The parsed buffer.

    Returns:
        The selected line's index into ``view.lines``, or ``None``.
    """
    if view.selected is not None:
        return view.selected[0]
    for index, line in enumerate(view.lines):
        if line.startswith("▶ ") or line.startswith("> "):
            return index
    return None


def _selection_range(view: ViewModel) -> tuple[int, int] | None:
    """Return the inclusive selection range, widening a caret row to a point."""
    if view.selected is not None:
        return view.selected
    line = selected_line(view)
    return None if line is None else (line, line)


def window(view: ViewModel, offset: int, height: int) -> list[str]:
    """Return the lines to draw: pinned sticky region then the scrolled body.

    The sticky region occupies the top rows unconditionally; the remaining rows
    show the body from *offset*, still honouring table-header pinning within the
    body (see :func:`~.sticky_window.pinned_window`).

    Args:
        view: The parsed buffer.
        offset: First body line to show (clamp with :func:`max_offset`).
        height: Total pane rows available.

    Returns:
        At most *height* display lines.
    """
    if view.sticky_count == 0:
        return pinned_window(view.lines, offset, height)
    head = view.lines[: view.sticky_count]
    body = view.lines[view.sticky_count :]
    body_height = max(height - view.sticky_count, 0)
    return head + pinned_window(body, offset, body_height)


def max_offset(view: ViewModel, height: int) -> int:
    """Return the largest valid body *offset* for a pane *height* rows tall."""
    body_height = max(height - view.sticky_count, 0)
    body_length = len(view.lines) - view.sticky_count
    return max(0, body_length - body_height)


def follow(view: ViewModel, offset: int, height: int) -> int:
    """Adjust the body *offset* so the selection stays visible.

    Starts from the supplied *offset* (letting callers propose a position, e.g.
    holding the caret at a fixed row while paging) and nudges it just enough to
    bring the selection into view below the sticky region. A selection taller
    than the body viewport is pinned to its top so its first line stays visible.

    Args:
        view: The parsed buffer.
        offset: Proposed first body line to show.
        height: Total pane rows available.

    Returns:
        A clamped body offset keeping the selection on screen.
    """
    body = view.lines[view.sticky_count :]
    body_height = max(height - view.sticky_count, 0)
    selection = _selection_range(view)
    if selection is None or body_height <= 0:
        return max(0, min(offset, max_offset(view, height)))

    start = selection[0] - view.sticky_count
    end = selection[1] - view.sticky_count
    reserved = reserved_top(body, start)
    if start - reserved < offset:
        offset = max(0, start - reserved)
    elif end >= offset + body_height:
        offset = end - body_height + 1
        if start - reserved < offset:  # selection overflows the viewport
            offset = max(0, start - reserved)
    return max(0, min(offset, max_offset(view, height)))
