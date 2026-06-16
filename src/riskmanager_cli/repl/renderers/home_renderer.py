"""Landing-screen renderer: the RISK MANAGER banner and the track cards.

The home screen is a pure landing menu — an ASCII banner above three cards
(``PROJECT``/``LIBRARY``/``ADMIN``). One card is highlighted at a time; the
caller supplies the highlighted index (driven by arrow-key navigation) and a
``bold`` styler so the renderer stays terminal-agnostic, mirroring how
``route_renderer`` receives a ``dim`` callable.
"""

from __future__ import annotations

from collections.abc import Callable

from ..viewport import tag_sticky
from .blocks import card_row, center_block
from .box import render_box
from .responsive import lay_out_row, widest_fitting

#: "RISK MANAGER" in the ANSI Shadow block font.
_BANNER: list[str] = [
    "██████╗ ██╗███████╗██╗  ██╗   ███╗   ███╗ █████╗ ███╗   ██╗ █████╗  ██████╗ ███████╗██████╗ ",
    "██╔══██╗██║██╔════╝██║ ██╔╝   ████╗ ████║██╔══██╗████╗  ██║██╔══██╗██╔════╝ ██╔════╝██╔══██╗",
    "██████╔╝██║███████╗█████╔╝    ██╔████╔██║███████║██╔██╗ ██║███████║██║  ███╗█████╗  ██████╔╝",
    "██╔══██╗██║╚════██║██╔═██╗    ██║╚██╔╝██║██╔══██║██║╚██╗██║██╔══██║██║   ██║██╔══╝  ██╔══██╗",
    "██║  ██║██║███████║██║  ██╗   ██║ ╚═╝ ██║██║  ██║██║ ╚████║██║  ██║╚██████╔╝███████╗██║  ██║",
    "╚═╝  ╚═╝╚═╝╚══════╝╚═╝  ╚═╝  ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝",
]

#: "Risk Manager" in the Standard figlet font — the mid-size step between the
#: full block banner and the small framed title.
_BANNER_MEDIUM: list[str] = [
    r"______ _     _     ___  ___",
    r"| ___ (_)   | |    |  \/  |",
    r"| |_/ /_ ___| | __ | .  . | __ _ _ __   __ _  __ _  ___ _ __",
    r"|    /| / __| |/ / | |\/| |/ _` | '_ \ / _` |/ _` |/ _ \ '__|",
    r"| |\ \| \__ \   <  | |  | | (_| | | | | (_| | (_| |  __/ |",
    r"\_| \_|_|___/_|\_\ \_|  |_/\__,_|_| |_|\__,_|\__, |\___|_|",
    r"                                              __/ |",
    r"                                             |___/",
]

#: Small framed title for terminals too narrow for either figlet block but wide
#: enough to avoid the bare text fallback.
_BANNER_COMPACT: list[str] = [
    "╔═══════════════════════════╗",
    "║  R I S K   M A N A G E R  ║",
    "╚═══════════════════════════╝",
]

#: Plain title shown when the terminal is too narrow for any banner block.
_FALLBACK_TITLE = "RISK MANAGER"

#: Track key, display title, and hotkey for each landing card, in display order.
#: The order must match the home navigator's item order so the highlighted index
#: lines up with the right card.
CARDS: list[tuple[str, str, str]] = [
    ("project", "P R O J E C T", "^P"),
    ("library", "L I B R A R Y", "^B"),
    ("admin", "A D M I N", "^N"),
]

# The output pane draws each line from column 1 and reserves the last column,
# so the drawable width is two columns short of the terminal (one margin each
# side). Lay the landing screen out within that, mirroring how the table screens
# subtract their own inset, or the rightmost card/banner column is clipped.
_SCREEN_INSET = 2

_CARD_WIDTH = 28
_CARD_GAP = 4
#: Narrowest a card may shrink to before its longest title ("L I B R A R Y", 13
#: columns) would clip inside ``render_box`` (2 borders + 2×2 padding = 6). Below
#: a side-by-side row of these (``3×19 + 2×4`` ≈ 65 columns) the cards stack.
_CARD_MIN_WIDTH = 19


def render_home(selected_index: int, *, width: int, bold: Callable[[str], str]) -> list[str]:
    """Render the landing screen: the banner above the three track cards.

    The layout is responsive to *width*: the banner steps down through the full
    block, a mid-size figlet, a small framed title and finally plain text, and
    the cards shrink toward :data:`_CARD_MIN_WIDTH` before stacking vertically
    once they no longer fit in a row (see :func:`responsive.lay_out_row`).

    Args:
        selected_index: Index into :data:`CARDS` of the highlighted card; the
            whole card is rendered bold. A negative index highlights nothing.
        width: Current terminal width, used to size and centre the banner and
            cards.
        bold: Styler applied to every line of the highlighted card.

    Returns:
        The composed home-screen lines.
    """
    inner = max(width - _SCREEN_INSET, 0)
    banner = widest_fitting([_BANNER, _BANNER_MEDIUM, _BANNER_COMPACT, [_FALLBACK_TITLE]], inner)
    # The banner is pinned to the top of the pane so it stays visible while the
    # cards scroll under it on a short terminal (see :mod:`~.repl.viewport`).
    lines = tag_sticky(center_block(banner, inner))
    lines.extend(["", ""])

    plan = lay_out_row(
        len(CARDS),
        item_min=_CARD_MIN_WIDTH,
        item_ideal=_CARD_WIDTH,
        gap=_CARD_GAP,
        available=inner,
    )
    cards: list[list[str]] = []
    for index, (_key, title, hotkey) in enumerate(CARDS):
        box = render_box([title, "", hotkey], plan.item_width, pad_y=2)
        if index == selected_index:
            box = [bold(line) for line in box]
        cards.append(box)

    lines.extend(
        card_row(
            cards,
            width=inner,
            gap=_CARD_GAP,
            selected_index=selected_index,
            stacked=plan.stacked,
        )
    )
    return lines
