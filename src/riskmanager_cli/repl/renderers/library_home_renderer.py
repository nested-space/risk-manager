"""Render the Library home page: a guide above a tabbed overview/information pane.

Unlike the subsection tables (:mod:`library_renderer`), this is the landing page
for the Library track. It opens with a pinned title and a short "about" paragraph,
then a box-drawn :func:`~.layout.tabpane` with two tabs:

* **Libraries** — a row of three navigable stat cards (NCRMs, Materials,
  Counterions) showing live record counts; this tab doubles as the subsection
  picker, so the caller supplies the highlighted index and ``Enter`` opens that
  subsection's table.
* **Information** — two side-by-side cards listing supported and not-yet-supported
  capabilities.

The active tab is supplied by the caller (toggled with ``Tab`` in the REPL loop).
The renderer stays pure and terminal-agnostic — it composes the shared layout
engine and never touches a terminal.
"""

from __future__ import annotations

from collections.abc import Callable

from ...repl_engine.layout import (
    bullet_list,
    card,
    card_row,
    center_block,
    join_horizontal,
    lay_out_row,
    tabpane,
    text_area,
    title,
    vstack,
)
from ...repl_engine.viewport import parse, tag_selected, tag_sticky

#: Library track title shown (pinned) at the top of the home page.
_TITLE = "Risk Manager Library"

#: Tab labels for the home pane, in display order. Exported so the dispatcher
#: cycles the active index over the same set.
LIBRARY_HOME_TABS: tuple[str, ...] = ("Libraries", "Information")

#: One-paragraph description of the Library track, wrapped to the terminal width.
_ABOUT = (
    "The Library is the interface for the key chemical entities Risk Manager "
    "draws on — materials, NCRMs and counterions. Each subsection is a "
    "searchable, validated table backed by the same operations layer as the "
    "rest of the application, so edits made here flow through to every project "
    "that references them."
)

#: Capabilities the Library currently provides, one bullet each.
_SUPPORTED = [
    "Create, Read, Update and Delete operations",
    "Real-time validation and uniqueness checking",
    "Search and filtering operations",
    "DMTA and PubChem augmentation for import",
]

#: Capabilities not yet available, one bullet each.
_UNSUPPORTED = [
    "Chemical structure visualisation",
    "Multi-select and bulk operations (other than import)",
    "Advanced filtering operations",
    "Audit logging and change tracking",
    "Export capabilities (CSV, Excel)",
]

#: Subsection key and display title for each Database Overview card, in display
#: order. Exported so the dispatcher builds its navigator items from the same
#: source of truth, keeping the highlighted index aligned with the right card.
OVERVIEW_CARDS: list[tuple[str, str]] = [
    ("ncrm", "NCRMs"),
    ("materials", "Materials"),
    ("counterions", "Counterions"),
]

# The output pane draws from column 1 and reserves the last column, so the
# drawable width is two columns short of the terminal — lay the page out within
# that, mirroring the landing screen, or the rightmost card column is clipped.
_SCREEN_INSET = 2

# Tab body overhead: the tabpane's two ``│`` walls, so the body field is the pane
# width less this.
_TAB_BODY_OVERHEAD = 2

# The three header rows a tabpane draws before its body (tab tops, labels,
# connector); body row ``i`` therefore lands at output row ``3 + i``.
_TAB_HEADER_ROWS = 3

# render_box overhead: two borders plus ``pad_x`` (2) columns of interior padding
# on each side, so the wrappable content field is the card width less this.
_BOX_OVERHEAD = 6

_FEATURE_CARD_WIDTH = 44
_FEATURE_CARD_MIN_WIDTH = 28
_FEATURE_GAP = 4

# The narrowest a stat card may shrink to before its longest title
# ("Counterions", 11 columns) would overflow the card's content field; below this
# the cards stack instead.
_STAT_CARD_WIDTH = 24
_STAT_CARD_MIN_WIDTH = 18
_STAT_GAP = 4


def _libraries_body(
    counts: dict[str, int], selected_index: int, field: int, bold: Callable[[str], str]
) -> list[str]:
    """Build the Libraries tab: the three navigable Database Overview cards.

    The *selected_index* card is bolded and tagged as the selection (via
    :func:`~.layout.card_row`) so the viewport keeps it on screen while scrolling.
    """
    plan = lay_out_row(
        len(OVERVIEW_CARDS),
        item_min=_STAT_CARD_MIN_WIDTH,
        item_ideal=_STAT_CARD_WIDTH,
        gap=_STAT_GAP,
        available=field,
    )
    cards: list[list[str]] = []
    for index, (key, heading) in enumerate(OVERVIEW_CARDS):
        box = card(heading, [str(counts.get(key, 0))], width=plan.item_width, pad_y=2)
        if index == selected_index:
            box = [bold(line) for line in box]
        cards.append(box)
    return card_row(
        cards, width=field, gap=_STAT_GAP, selected_index=selected_index, stacked=plan.stacked
    )


def _information_body(field: int) -> list[str]:
    """Build the Information tab: the supported / not-supported capability cards.

    The cards shrink toward :data:`_FEATURE_CARD_MIN_WIDTH` and stack vertically
    once they no longer fit side by side. Their bullet bodies are padded to a
    common height so the two framed boxes line up when drawn in a row.
    """
    plan = lay_out_row(
        2,
        item_min=_FEATURE_CARD_MIN_WIDTH,
        item_ideal=_FEATURE_CARD_WIDTH,
        gap=_FEATURE_GAP,
        available=field,
    )
    # Stacked cards keep their floor even when the terminal is narrower; clamp to
    # the drawable field so a single card never overruns the body.
    card_width = min(plan.item_width, field)
    content_field = max(card_width - _BOX_OVERHEAD, 1)
    sections = [("Currently Supported", _SUPPORTED), ("Not Yet Supported", _UNSUPPORTED)]
    bodies = [bullet_list(items, content_field) for _, items in sections]
    height = max(len(body) for body in bodies)
    boxes = [
        card(heading, [*body, *([""] * (height - len(body)))], width=card_width, align="left")
        for (heading, _), body in zip(sections, bodies, strict=True)
    ]
    if plan.stacked:
        return vstack(boxes, gap=1, align="center", width=field)
    return center_block(join_horizontal(boxes, _FEATURE_GAP), field)


def render_library_home(
    counts: dict[str, int],
    selected_index: int,
    *,
    active_tab: int = 0,
    width: int,
    bold: Callable[[str], str],
) -> list[str]:
    """Render the Library home page.

    Args:
        counts: Record counts keyed by subsection (``ncrm``/``materials``/
            ``counterions``); missing keys render as ``0``.
        selected_index: Index into :data:`OVERVIEW_CARDS` of the highlighted
            overview card on the Libraries tab; that card is rendered bold. A
            negative index highlights nothing (e.g. on the Information tab).
        active_tab: Index into :data:`LIBRARY_HOME_TABS` of the open tab.
        width: Current terminal width, used to size and centre every section.
        bold: Styler applied to the highlighted card and the active tab label.

    Returns:
        The composed home-page lines: a pinned title, the About paragraph, then
        the tabbed pane (selection tagged when the Libraries tab is open).
    """
    inner = max(width - _SCREEN_INSET, 0)
    field = max(inner - _TAB_BODY_OVERHEAD, 0)

    # Only the title is pinned, so it stays visible while the guide scrolls.
    lines = tag_sticky(title(_TITLE))
    lines += ["", *text_area(_ABOUT, inner), ""]

    if active_tab == 0:
        body = _libraries_body(counts, selected_index, field, bold)
    else:
        body = _information_body(field)

    # The card row tags its selection, but those tags would be buried inside the
    # tabpane's framing. Strip them, frame the clean body, then re-tag the matching
    # output rows so the viewport still keeps the selected card on screen.
    view = parse(body)
    pane = tabpane(list(LIBRARY_HOME_TABS), active_tab, view.lines, width=inner, emphasize=bold)
    if view.selected is not None:
        start, end = view.selected
        for offset in range(start, end + 1):
            row = _TAB_HEADER_ROWS + offset
            pane[row] = tag_selected([pane[row]])[0]

    lines += pane
    return lines
