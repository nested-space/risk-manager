"""Arrow-key list navigation primitives for home and route selection views."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ListItem:
    """One selectable item in a REPL list view.

    Attributes:
        label: Primary display label.
        subtitle: Optional secondary text.
        item_id: Stable identifier for selection actions.
    """

    label: str
    subtitle: str = ""
    item_id: str = ""


class ListNavigator:
    """Track selection and render grouped recent/all item lists."""

    def __init__(
        self,
        recents: list[ListItem],
        all_items: list[ListItem],
    ) -> None:
        """Create a navigator for grouped recent and full item lists.

        Args:
            recents: Recently used items.
            all_items: Full set of items.
        """
        self._recents = recents
        self._all_items = all_items
        self._items = [*recents, *all_items]
        self._selected_index = 0 if self._items else -1

    def move_up(self) -> None:
        """Move the cursor upward, wrapping to the end when needed."""
        if not self._items:
            return
        self._selected_index = (self._selected_index - 1) % len(self._items)

    def move_down(self) -> None:
        """Move the cursor downward, wrapping to the start when needed."""
        if not self._items:
            return
        self._selected_index = (self._selected_index + 1) % len(self._items)

    def move(self, delta: int) -> None:
        """Move the cursor by *delta* items, clamped to the list ends.

        Unlike :meth:`move_up`/:meth:`move_down`, this does not wrap: it is used
        for paging (PgUp/PgDn), where overshooting should land on the first or
        last item rather than jumping to the opposite end. No-op on an empty list.

        Args:
            delta: Signed number of items to move; positive moves downward.
        """
        if not self._items:
            return
        self._selected_index = max(0, min(self._selected_index + delta, len(self._items) - 1))

    @property
    def selected(self) -> ListItem | None:
        """Return the currently selected item, if any."""
        if self._selected_index < 0:
            return None
        return self._items[self._selected_index]

    def select_item_id(self, item_id: str) -> None:
        """Highlight the item whose ``item_id`` matches *item_id*, if present.

        Args:
            item_id: Identifier of the item to highlight.
        """
        for index, item in enumerate(self._items):
            if item.item_id == item_id:
                self._selected_index = index
                return

    def render_lines(
        self,
        width: int,
        *,
        show_sections: bool = True,
        subtitle_style: Callable[[str], str] | None = None,
    ) -> list[str]:
        """Render items for display, optionally grouped under section headers.

        Args:
            width: Maximum terminal width in characters.
            show_sections: When ``True`` (the full-screen lists), prefix the
                ``Recent``/``All`` group headers. When ``False`` (modal choosers
                and pickers, which never carry recents), render a bare list.
            subtitle_style: When provided, subtitles are aligned into a shared
                column and the styler is applied to each (e.g. to dim it). When
                ``None``, subtitles are appended plain (legacy behaviour).

        Returns:
            Renderable output lines.
        """
        if not self._items:
            return ["No items available."]

        label_col = self._label_column_width(width) if subtitle_style else 0

        def render(item: ListItem, index: int) -> str:
            return self._render_item(
                item,
                index == self._selected_index,
                width,
                label_col=label_col,
                subtitle_style=subtitle_style,
            )

        if not show_sections:
            return [render(item, index) for index, item in enumerate(self._items)]

        lines: list[str] = []
        offset = 0
        if self._recents:
            lines.append("Recent")
            for index, item in enumerate(self._recents):
                lines.append(render(item, index))
            offset = len(self._recents)
            lines.append("")
        lines.append("All")
        for index, item in enumerate(self._all_items, start=offset):
            lines.append(render(item, index))
        return lines

    def _label_column_width(self, width: int) -> int:
        """Width to pad labels to so subtitles align, capped to leave subtitle room."""
        widest = max((len(item.label) for item in self._items if item.subtitle), default=0)
        cap = max((width - 2) * 2 // 3, 1)
        return min(widest, cap)

    def handle_key(self, key: str) -> ListItem | None:
        """Handle a navigation key.

        Args:
            key: Blessed key name or literal character.

        Returns:
            The selected item when Enter is pressed; otherwise ``None``.
        """
        if key in {"KEY_UP", "k", "\x1b[A"}:
            self.move_up()
            return None
        if key in {"KEY_DOWN", "j", "\x1b[B"}:
            self.move_down()
            return None
        if key in {"KEY_ENTER", "\n", "\r"}:
            return self.selected
        return None

    @staticmethod
    def _render_item(
        item: ListItem,
        selected: bool,
        width: int,
        *,
        label_col: int = 0,
        subtitle_style: Callable[[str], str] | None = None,
    ) -> str:
        prefix = "▶ " if selected else "  "
        avail = max(width - len(prefix), 0)
        if subtitle_style is None or not item.subtitle:
            suffix = f" {item.subtitle}" if item.subtitle else ""
            return f"{prefix}{(item.label + suffix)[:avail]}"
        # Lay out (and truncate) on plain text, then style only the surviving
        # subtitle substring — applying ANSI before truncation would corrupt it.
        column = item.label[:avail].ljust(label_col)
        remaining = avail - len(column) - 2
        if remaining <= 0:
            return f"{prefix}{column[:avail]}"
        subtitle = item.subtitle[:remaining]
        return f"{prefix}{column}  {subtitle_style(subtitle)}"
