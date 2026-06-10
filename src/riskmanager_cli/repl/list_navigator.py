"""Arrow-key list navigation primitives for home and route selection views."""

from __future__ import annotations

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

    def render_lines(self, width: int) -> list[str]:
        """Render section headers and items for display.

        Args:
            width: Maximum terminal width in characters.

        Returns:
            Renderable output lines.
        """
        if not self._items:
            return ["No items available."]

        lines: list[str] = []
        offset = 0
        if self._recents:
            lines.append("Recent")
            for index, item in enumerate(self._recents):
                lines.append(self._render_item(item, index == self._selected_index, width))
            offset = len(self._recents)
            lines.append("")
        lines.append("All")
        for index, item in enumerate(self._all_items, start=offset):
            lines.append(self._render_item(item, index == self._selected_index, width))
        return lines

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
    def _render_item(item: ListItem, selected: bool, width: int) -> str:
        prefix = "▶ " if selected else "  "
        suffix = f" {item.subtitle}" if item.subtitle else ""
        return f"{prefix}{(item.label + suffix)[: max(width - len(prefix), 0)]}"
