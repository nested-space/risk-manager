"""Landing-screen renderer: the RISK MANAGER banner and the track cards.

The home screen is a pure landing menu — an ASCII banner above three cards
(``PROJECT``/``LIBRARY``/``ADMIN``). One card is highlighted at a time; the
caller supplies the highlighted index (driven by arrow-key navigation) and a
``bold`` styler so the renderer stays terminal-agnostic, mirroring how
``route_renderer`` receives a ``dim`` callable.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .box import render_box

# Matches CSI/SGR escape sequences so block widths count only printable columns.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

#: "RISK MANAGER" in the ANSI Shadow block font.
_BANNER: list[str] = [
    "██████╗ ██╗███████╗██╗  ██╗   ███╗   ███╗ █████╗ ███╗   ██╗ █████╗  ██████╗ ███████╗██████╗ ",
    "██╔══██╗██║██╔════╝██║ ██╔╝   ████╗ ████║██╔══██╗████╗  ██║██╔══██╗██╔════╝ ██╔════╝██╔══██╗",
    "██████╔╝██║███████╗█████╔╝    ██╔████╔██║███████║██╔██╗ ██║███████║██║  ███╗█████╗  ██████╔╝",
    "██╔══██╗██║╚════██║██╔═██╗    ██║╚██╔╝██║██╔══██║██║╚██╗██║██╔══██║██║   ██║██╔══╝  ██╔══██╗",
    "██║  ██║██║███████║██║  ██╗   ██║ ╚═╝ ██║██║  ██║██║ ╚████║██║  ██║╚██████╔╝███████╗██║  ██║",
    "╚═╝  ╚═╝╚═╝╚══════╝╚═╝  ╚═╝  ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝",
]

#: Compact title shown when the terminal is too narrow for the block banner.
_FALLBACK_TITLE = "RISK MANAGER"

#: Track key, display title, and hotkey for each landing card, in display order.
#: The order must match the home navigator's item order so the highlighted index
#: lines up with the right card.
CARDS: list[tuple[str, str, str]] = [
    ("project", "P R O J E C T", "^P"),
    ("library", "L I B R A R Y", "^B"),
    ("admin", "A D M I N", "^N"),
]

_CARD_WIDTH = 28
_CARD_GAP = 4


def _visible_len(text: str) -> int:
    """Return the printable column width of *text*, ignoring ANSI escapes."""
    return len(_ANSI_RE.sub("", text))


def _block_width(lines: list[str]) -> int:
    """Return the widest visible line width in a block."""
    return max((_visible_len(line) for line in lines), default=0)


def _center_block(lines: list[str], width: int) -> list[str]:
    """Indent every line by a shared left margin so the block is centred in *width*."""
    margin = max((width - _block_width(lines)) // 2, 0)
    pad = " " * margin
    return [f"{pad}{line}" for line in lines]


def _join_horizontal(blocks: list[list[str]], gap: int) -> list[str]:
    """Concatenate equal-or-ragged box blocks side by side with a *gap* between them.

    Each block is padded to the tallest block's height and to its own widest
    visible line, so a uniform spacer keeps the columns aligned even when blocks
    carry ANSI styling.

    Args:
        blocks: One list of display lines per column.
        gap: Number of blank columns between adjacent blocks.

    Returns:
        The merged rows spanning all blocks.
    """
    height = max((len(block) for block in blocks), default=0)
    padded: list[list[str]] = []
    for block in blocks:
        block_width = _block_width(block)
        rows = [*block, *([""] * (height - len(block)))]
        padded.append([line + " " * (block_width - _visible_len(line)) for line in rows])
    spacer = " " * gap
    return [spacer.join(parts) for parts in zip(*padded)]


def render_home(selected_index: int, *, width: int, bold: Callable[[str], str]) -> list[str]:
    """Render the landing screen: the banner above the three track cards.

    Args:
        selected_index: Index into :data:`CARDS` of the highlighted card; the
            whole card is rendered bold. A negative index highlights nothing.
        width: Current terminal width, used to centre the banner and cards.
        bold: Styler applied to every line of the highlighted card.

    Returns:
        The composed home-screen lines.
    """
    banner = _BANNER if _block_width(_BANNER) <= width else [_FALLBACK_TITLE]
    lines = _center_block(banner, width)
    lines.extend(["", ""])

    cards: list[list[str]] = []
    for index, (_key, title, hotkey) in enumerate(CARDS):
        box = render_box([title, "", hotkey], _CARD_WIDTH, pad_y=2)
        if index == selected_index:
            box = [bold(line) for line in box]
        cards.append(box)
    lines.extend(_center_block(_join_horizontal(cards, _CARD_GAP), width))
    return lines
