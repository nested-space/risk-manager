"""Blessed-backed screen drawing utilities for the riskmanager REPL."""

from __future__ import annotations

import sys

import blessed

from .context import ContextManager
from .viewport import ViewModel, parse, window


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
        """Return the number of rows available in the output pane.

        Five rows are reserved as chrome: the header, the overline, the
        underline, the input/nav row, and the info line.
        """
        return max(self._term.height - 5, 0)

    @property
    def width(self) -> int:
        """Return the current terminal width."""
        return self._term.width

    def dim(self, text: str) -> str:
        """Wrap *text* in the terminal's dim (greyed) styling."""
        return f"{self._term.dim}{text}{self._term.normal}"

    def bold(self, text: str) -> str:
        """Wrap *text* in the terminal's bold styling."""
        return f"{self._term.bold}{text}{self._term.normal}"

    def style_notice(self, message: str, level: str) -> str:
        """Wrap a status *message* in a colour matching its *level*.

        Args:
            message: Notice text.
            level: One of ``"success"`` (green), ``"warning"`` (amber), or
                ``"error"`` (red); anything else renders unstyled.

        Returns:
            The styled, terminal-ready string.
        """
        color = {
            "success": self._term.green,
            "warning": self._term.yellow,
            "error": self._term.red,
        }.get(level, self._term.normal)
        return f"{color}{message}{self._term.normal}"

    def draw_full(self, lines: list[str], input_line: str = "", info_line: str = "") -> None:
        """Fully repaint the screen.

        Args:
            lines: Output pane lines.
            input_line: Current input buffer content.
            info_line: Command-hint text for the bottom information line.
        """
        self.clear_screen()
        self.draw_status_bar()
        self.draw_output(parse(lines))
        self.draw_input_line(text=input_line)
        self.draw_info_line(info_line)

    def draw_status_bar(self) -> None:
        """Render the single-row header: breadcrumb left, mode right."""
        self._write_header_row(self._ctx.breadcrumb(), self._ctx.mode_label())
        sys.stdout.flush()

    def draw_output(self, view: ViewModel, offset: int = 0) -> None:
        """Frame and fill the output pane: top spacer, content window, underline.

        Row 1 is a blank spacer in the default background — one line of breathing
        room below the header band. The underline (row ``height - 3``) is a fixed
        content rule. The scrollable content sits between them on rows
        ``2 … height - 4``.

        Content is inset by one blank column on each side: every line is drawn
        starting at column 1, and clipped so its last column stays blank. This
        mirrors the top/bottom breathing room created by the chrome, giving the
        centre panel matching horizontal margins.

        Args:
            view: Parsed output buffer (see :mod:`~.viewport`); may exceed the
                pane height.
            offset: Index of the first *body* line to show. The window is built
                by :func:`~.viewport.window`, which pins the sticky top region
                and any box-table header on screen; absent both it is a plain
                slice. Callers clamp *offset* via :func:`~.viewport.max_offset`.
        """
        width = self._term.width
        underline_row = max(self._term.height - 3, 2)
        sys.stdout.write(self._term.move_xy(0, 1) + self._term.clear_eol)
        for row in range(2, underline_row):
            sys.stdout.write(self._term.move_xy(0, row) + self._term.clear_eol)
        for row, line in enumerate(window(view, offset, self.output_height), start=2):
            sys.stdout.write(self._term.move_xy(1, row) + self._fit_width(line))
        sys.stdout.write(self._term.move_xy(0, underline_row) + self._term.clear_eol + "_" * width)
        sys.stdout.flush()

    def scroll_indicator(self, offset: int, total: int, *, height: int | None = None) -> str:
        """Return a dimmed scroll-position hint, or ``""`` when nothing overflows.

        Args:
            offset: Index of the first visible line.
            total: Total number of scrollable lines.
            height: Visible rows for the scrollable region; defaults to the full
                pane. Pass the body height (pane minus any pinned region) so the
                hint reflects what actually scrolls.

        Returns:
            A hint like ``"▲▼ scroll (12–34 of 80)"`` (arrows reflect whether
            content lies above/below the window), styled dim; empty when the
            content fits the pane.
        """
        if height is None:
            height = self.output_height
        if total <= height or height <= 0:
            return ""
        first = offset + 1
        last = min(offset + height, total)
        up = "▲" if offset > 0 else " "
        down = "▼" if offset + height < total else " "
        return self.dim(f"{up}{down} scroll ({first}–{last} of {total})")

    def _fit_width(self, line: str) -> str:
        """Truncate *line* to the inset content width by visible length.

        Content is drawn from column 1 with the final column held blank, so the
        usable width is two columns short of the terminal width — one reserved
        margin on each side.

        Plain slicing would corrupt lines containing escape sequences (e.g.
        dimmed text), so only clip when the *printable* length overruns; blessed
        ``Terminal.length`` ignores escape codes.
        """
        content_width = max(self._term.width - 2, 0)
        if self._term.length(line) <= content_width:
            return line
        return line[:content_width]

    def draw_input_line(self, prompt: str = "> ", text: str = "", notice: str = "") -> None:
        """Render the input line at the bottom row.

        Args:
            prompt: Prompt prefix.
            text: User-entered text.
            notice: Pre-styled status notice, right-aligned on the same row.
        """
        row = max(self._term.height - 2, 0)
        out = (
            self._term.move_xy(0, row)
            + self._term.clear_eol
            + self._with_notice(f"{prompt}{text}", notice)
        )
        sys.stdout.write(out)
        sys.stdout.flush()

    def draw_nav_hint(
        self,
        hint: str = "↑↓ to navigate  ·  Enter to select  ·  /search <name> to filter",
        notice: str = "",
    ) -> None:
        """Replace the input line with a list-navigation hint.

        Args:
            hint: Hint text to display.
            notice: Pre-styled status notice, right-aligned on the same row.
        """
        row = max(self._term.height - 2, 0)
        sys.stdout.write(
            self._term.move_xy(0, row) + self._term.clear_eol + self._with_notice(hint, notice)
        )
        sys.stdout.flush()

    def _with_notice(self, left: str, notice: str) -> str:
        """Append a right-aligned *notice* to *left*, fit to the terminal width.

        Printable width is measured with ``Terminal.length`` so embedded escape
        sequences are not clobbered. The notice is dropped when fewer than one
        column of separation remains, keeping the left content intact.
        """
        left_len = self._term.length(left)
        if not notice:
            return left[: self._term.width]
        gap = self._term.width - left_len - self._term.length(notice)
        if gap < 1:
            return left[: self._term.width]
        return left[: self._term.width] + (" " * gap) + notice

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

    def _write_header_row(self, left: str, right: str) -> None:
        """Render row 0 with *left* aligned left and *right* aligned right.

        The two labels share a single ``on_blue`` band spanning the full width.
        When they cannot both fit, the right label is dropped and the breadcrumb
        is padded to width on its own.
        """
        width = self._term.width
        if len(left) + len(right) + 1 > width:
            text = left[:width].ljust(width)
        else:
            text = left + " " * (width - len(left) - len(right)) + right
        styled = (
            self._term.move_xy(0, 0)
            + self._term.on_blue
            + self._term.bold
            + self._term.white
            + text
            + self._term.normal
        )
        sys.stdout.write(styled)
