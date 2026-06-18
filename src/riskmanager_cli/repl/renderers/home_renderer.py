"""Landing-screen renderer: the RISK MANAGER banner and the track cards.

The home screen is a pure landing menu — an ASCII banner above three cards
(``PROJECT``/``LIBRARY``/``ADMIN``). One card is highlighted at a time; the
caller supplies the highlighted index (driven by arrow-key navigation) and a
``bold`` styler so the renderer stays terminal-agnostic, mirroring how
``route_renderer`` receives a ``dim`` callable.
"""

from __future__ import annotations

from collections.abc import Callable

from ...repl_engine.layout import (
    Placement,
    card_row,
    center_block,
    lay_out_row,
    overlay,
    render_box,
    vstack,
    widest_fitting,
)
from ...repl_engine.viewport import parse, tag_selected, tag_sticky

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

#: Blank rows between the banner and the card row, preserved from the original
#: top-anchored layout so the vertically-centred box keeps the same spacing.
_TITLE_GAP = 2


def _card_boxes(
    selected_index: int, inner: int, bold: Callable[[str], str]
) -> tuple[list[list[str]], bool]:
    """Build the three framed track cards (bolding the selected one) and the
    row-vs-stack decision for the available width."""
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
    return cards, plan.stacked


def _compose_box(
    selected_index: int, inner: int, bold: Callable[[str], str]
) -> tuple[list[str], int, tuple[int, int] | None]:
    """Assemble the title-over-cards box and return it with its banner height and
    the (box-relative) selected-card range.

    The card row tags its own selection; that is recovered into a clean range here
    so the whole box can be composited and re-tagged at its centred position.
    """
    banner = widest_fitting([_BANNER, _BANNER_MEDIUM, _BANNER_COMPACT, [_FALLBACK_TITLE]], inner)
    banner_block = center_block(banner, inner)

    cards, stacked = _card_boxes(selected_index, inner, bold)
    cards_view = parse(
        card_row(cards, width=inner, gap=_CARD_GAP, selected_index=selected_index, stacked=stacked)
    )
    box = vstack([banner_block, cards_view.lines], gap=_TITLE_GAP, width=inner)

    selected = cards_view.selected
    if selected is not None:
        offset = len(banner_block) + _TITLE_GAP
        selected = (selected[0] + offset, selected[1] + offset)
    return box, len(banner_block), selected


def _retag(box: list[str], top: int, banner_height: int, selected: tuple[int, int] | None) -> None:
    """Re-apply the sticky/selected tags onto the composited (clean) *box* lines.

    Compositing through the StackPane strips the role tags (overlay measures by
    visible width and would mismeasure the control prefixes), so they are restored
    by row index here. The banner is pinned only when the box is top-anchored
    (``top == 0``); once it is vertically centred the content fits the pane and
    nothing scrolls, so there is nothing to pin.
    """
    if selected is not None:
        for row in range(top + selected[0], top + selected[1] + 1):
            box[row] = tag_selected([box[row]])[0]
    if top == 0:
        for row in range(banner_height):
            box[row] = tag_sticky([box[row]])[0]


def render_home(
    selected_index: int, *, width: int, height: int, bold: Callable[[str], str]
) -> list[str]:
    """Render the landing screen: the banner above the three track cards.

    The banner and cards are composed into a single vertical box (title, a fixed
    gap, then the card row) and that box is centred within the pane by the
    StackPane (:func:`~.layout.overlay`): vertically centred when it fits *height*,
    and otherwise top-anchored so the banner stays pinned and the cards scroll
    under it on a short terminal (see :mod:`~.repl.viewport`).

    The layout is also responsive to *width*: the banner steps down through the
    full block, a mid-size figlet, a small framed title and finally plain text,
    and the cards shrink toward :data:`_CARD_MIN_WIDTH` before stacking vertically
    once they no longer fit in a row (see :func:`responsive.lay_out_row`).

    Args:
        selected_index: Index into :data:`CARDS` of the highlighted card; the
            whole card is rendered bold. A negative index highlights nothing.
        width: Current terminal width, used to size and centre the banner and
            cards.
        height: Output-pane height in rows, used to centre the box vertically.
        bold: Styler applied to every line of the highlighted card.

    Returns:
        The composed home-screen lines.
    """
    inner = max(width - _SCREEN_INSET, 0)
    box, banner_height, selected = _compose_box(selected_index, inner, bold)

    pane_height = max(height, 0)
    if len(box) >= pane_height:
        # The box fills or overflows the pane: keep it top-anchored so it scrolls
        # under the pinned banner rather than being clipped by the canvas.
        top = 0
    else:
        top = (pane_height - len(box)) // 2
        box = overlay(inner, pane_height, [Placement(box, valign="middle")])

    # ``selected`` is box-relative; ``_retag`` shifts it by ``top``.
    _retag(box, top, banner_height, selected)
    return box
