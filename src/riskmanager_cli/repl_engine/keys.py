"""Keystroke classification for the blessed event loop.

These predicates translate raw :class:`blessed.keyboard.Keystroke` events into
the small set of categories the loop branches on. They are pure and stateless,
so they are equally useful to tests that synthesise keystrokes.
"""

from __future__ import annotations

import blessed


def is_scroll_key(key_name: str, key_text: str) -> bool:
    """Return ``True`` for a content-scroll key.

    PgUp/PgDown page the view; Ctrl+Up/Ctrl+Down nudge it one line. blessed
    resolves the Ctrl+arrow combos to ``KEY_CTRL_UP``/``KEY_CTRL_DOWN`` on most
    terminals; the raw xterm sequences are matched as a fallback.
    """
    return key_name in {"KEY_PGUP", "KEY_PGDOWN", "KEY_CTRL_UP", "KEY_CTRL_DOWN"} or key_text in {
        "\x1b[1;5A",
        "\x1b[1;5B",
    }


def is_enter(key_name: str, key_text: str) -> bool:
    """Return ``True`` for the Enter/Return key."""
    return key_name == "KEY_ENTER" or key_text in {"\n", "\r"}


def is_backspace(key_name: str, key_text: str) -> bool:
    """Return ``True`` for the Backspace/Delete key."""
    return key_name in {"KEY_BACKSPACE", "KEY_DELETE"} or key_text in {"\b", "\x7f"}


def is_text_input(key: blessed.keyboard.Keystroke) -> bool:
    """Return ``True`` when *key* is a printable, non-sequence character."""
    text = str(key)
    return bool(text) and not key.is_sequence and text.isprintable()


def is_hotkey(key: blessed.keyboard.Keystroke, key_text: str) -> bool:
    """Return ``True`` for a Ctrl-<letter> hotkey keystroke.

    Control characters arrive as a single byte below ``0x20`` and are not part
    of an escape sequence (arrow keys are). Ctrl-C/D, Enter, Tab, and Backspace
    are handled earlier, so they never reach this check.
    """
    return not key.is_sequence and len(key_text) == 1 and ord(key_text) < 0x20
