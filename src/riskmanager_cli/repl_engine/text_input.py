"""Cursor-aware single-line text editor for in-place modal field editing.

This is the application-agnostic editing model behind a text/numeric prompt
field. It owns the in-progress value and a cursor offset, exposing the small set
of edits the event loop binds to keystrokes (insert, backspace, delete, and
cursor movement). Rendering lives in :mod:`forms`; this module is pure and
unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LineEditor:
    """An editable line of text with a cursor offset.

    The cursor is an index in ``[0, len(text)]`` marking the gap where the next
    insertion lands: ``0`` is before the first character and ``len(text)`` is
    after the last. Every mutator clamps the cursor so it can never leave that
    range.

    Attributes:
        text: The current value.
        cursor: Insertion point within ``text``.
    """

    text: str = ""
    cursor: int = 0

    @classmethod
    def from_text(cls, text: str) -> LineEditor:
        """Return an editor seeded with *text* and the cursor at its end."""
        return cls(text=text, cursor=len(text))

    def insert(self, chars: str) -> None:
        """Insert *chars* at the cursor and advance past them."""
        self.text = self.text[: self.cursor] + chars + self.text[self.cursor :]
        self.cursor += len(chars)

    def backspace(self) -> None:
        """Delete the character before the cursor, if any."""
        if self.cursor > 0:
            self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
            self.cursor -= 1

    def delete(self) -> None:
        """Delete the character at the cursor, if any."""
        if self.cursor < len(self.text):
            self.text = self.text[: self.cursor] + self.text[self.cursor + 1 :]

    def left(self) -> None:
        """Move the cursor one character left, clamped at the start."""
        self.cursor = max(0, self.cursor - 1)

    def right(self) -> None:
        """Move the cursor one character right, clamped at the end."""
        self.cursor = min(len(self.text), self.cursor + 1)

    def home(self) -> None:
        """Move the cursor to the start of the line."""
        self.cursor = 0

    def end(self) -> None:
        """Move the cursor to the end of the line."""
        self.cursor = len(self.text)
