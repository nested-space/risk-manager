"""Blessed-backed screen drawing utilities for the riskmanager REPL."""

from __future__ import annotations

import sys

import blessed

from .context import ContextManager


class ScreenManager:
    """Draw the status bar, output pane, and input line."""

    def __init__(self, term: blessed.Terminal, ctx: ContextManager) -> None:
        """Create a screen manager for *term* and *ctx*.

        Args:
            term: Active blessed terminal instance.
            ctx: Navigation context manager.
        """
        self._term = term
        self._ctx = ctx

    @property
    def output_height(self) -> int:
        """Return the number of rows available in the output pane."""
        return max(self._term.height - 4, 0)

    @property
    def width(self) -> int:
        """Return the current terminal width."""
        return self._term.width

    def draw_full(self, lines: list[str], input_line: str = "", info_line: str = "") -> None:
        """Fully repaint the screen.

        Args:
            lines: Output pane lines.
            input_line: Current input buffer content.
            info_line: Command-hint text for the bottom information line.
        """
        self.clear_screen()
        self.draw_status_bar()
        self.draw_output(lines)
        self.draw_input_line(text=input_line)
        self.draw_info_line(info_line)

    def draw_status_bar(self) -> None:
        """Render the two-line status bar."""
        self._write_status_row(0, self._ctx.breadcrumb())
        self._write_status_row(1, self._ctx.mode_label())
        sys.stdout.flush()

    def draw_output(self, lines: list[str]) -> None:
        """Clear the output pane and write lines, truncating to fit."""
        for row in range(2, max(self._term.height - 2, 2)):
            sys.stdout.write(self._term.move_xy(0, row) + self._term.clear_eol)
        for offset, line in enumerate(lines[: self.output_height], start=2):
            sys.stdout.write(self._term.move_xy(0, offset) + line[: self._term.width])
        sys.stdout.flush()

    def draw_input_line(self, prompt: str = "> ", text: str = "") -> None:
        """Render the input line at the bottom row.

        Args:
            prompt: Prompt prefix.
            text: User-entered text.
        """
        row = max(self._term.height - 2, 0)
        content = f"{prompt}{text}"[: self._term.width]
        sys.stdout.write(self._term.move_xy(0, row) + self._term.clear_eol + content)
        sys.stdout.flush()

    def draw_nav_hint(
        self,
        hint: str = "↑↓ to navigate  ·  Enter to select  ·  /search <name> to filter",
    ) -> None:
        """Replace the input line with a list-navigation hint.

        Args:
            hint: Hint text to display.
        """
        row = max(self._term.height - 2, 0)
        sys.stdout.write(
            self._term.move_xy(0, row) + self._term.clear_eol + hint[: self._term.width]
        )
        sys.stdout.flush()

    def draw_info_line(self, hints: str = "") -> None:
        """Render the command-hint information line at the bottom row.

        Args:
            hints: Command-hint text to display, dimmed and truncated to width.
        """
        row = max(self._term.height - 1, 0)
        width = self._term.width
        text = hints
        if len(text) > width:
            text = text[: max(width - 1, 0)] + ("…" if width >= 1 else "")
        sys.stdout.write(
            self._term.move_xy(0, row)
            + self._term.clear_eol
            + self._term.dim
            + text
            + self._term.normal
        )
        sys.stdout.flush()

    def clear_screen(self) -> None:
        """Clear the full terminal screen and move the cursor home."""
        sys.stdout.write(self._term.home + self._term.clear)
        sys.stdout.flush()

    def _write_status_row(self, row: int, text: str) -> None:
        styled = (
            self._term.move_xy(0, row)
            + self._term.on_blue
            + self._term.bold
            + self._term.white
            + text[: self._term.width].ljust(self._term.width)
            + self._term.normal
        )
        sys.stdout.write(styled)
