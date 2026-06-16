"""Render the Library home page: a guide screen above three navigable stat cards.

Unlike the subsection tables (:mod:`library_renderer`), this is the landing page
for the Library track. It opens with a short "About This Tool" paragraph and two
side-by-side info cards (supported / not-yet-supported capabilities), then a
``Database Overview`` row of three cards — NCRMs, Materials and Counterions —
showing live record counts.

The overview cards double as the subsection picker: the caller supplies the
highlighted index (driven by arrow keys, matching :data:`OVERVIEW_CARDS`) and a
``bold`` styler, mirroring :func:`home_renderer.render_home`, and ``Enter`` on a
card opens that subsection's table. The renderer stays pure and
terminal-agnostic — it composes the shared box/block/responsive primitives and
never touches a terminal.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable

from ..viewport import tag_sticky
from .blocks import card_row, center_block, join_horizontal
from .box import render_box
from .responsive import lay_out_row
from .tables import section_rule, section_width

#: Library track title shown at the top of the home page.
_TITLE = "Risk Manager Library"

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

# render_box overhead: two borders plus ``pad_x`` (2) columns of interior padding
# on each side, so the wrappable content field is the card width less this.
_BOX_OVERHEAD = 6

_FEATURE_CARD_WIDTH = 44
_FEATURE_CARD_MIN_WIDTH = 28
_FEATURE_GAP = 4

# The narrowest a stat card may shrink to before its longest title
# ("Counterions", 11 columns) would overflow render_box's content field
# (item_width − :data:`_BOX_OVERHEAD`); below this the cards stack instead.
_STAT_CARD_WIDTH = 24
_STAT_CARD_MIN_WIDTH = 18
_STAT_GAP = 4


def _feature_card(title: str, bullets: list[str], field: int) -> list[str]:
    """Build a feature card's content lines: a title, a blank, then wrapped bullets.

    Each bullet is wrapped to *field* columns with a hanging indent so the ``•``
    marker stays in the left gutter and continuation lines align under the text.

    Args:
        title: Card heading.
        bullets: Bullet strings (unwrapped).
        field: Content width available inside the box borders and padding.

    Returns:
        The card's content lines, ready to frame with :func:`render_box`.
    """
    lines = [title, ""]
    for bullet in bullets:
        wrapped = textwrap.wrap(
            bullet, width=max(field, 1), initial_indent="• ", subsequent_indent="  "
        )
        lines.extend(wrapped or [f"• {bullet}"])
    return lines


def _feature_cards(width: int) -> list[str]:
    """Render the supported / not-supported info cards for the available *width*.

    The cards shrink toward :data:`_FEATURE_CARD_MIN_WIDTH` and stack vertically
    once they no longer fit side by side. Their content is padded to a common
    height so the two framed boxes line up when drawn in a row.
    """
    plan = lay_out_row(
        2,
        item_min=_FEATURE_CARD_MIN_WIDTH,
        item_ideal=_FEATURE_CARD_WIDTH,
        gap=_FEATURE_GAP,
        available=width,
    )
    # Stacked cards keep their floor even when the terminal is narrower; clamp to
    # the drawable width so a single card never overruns the pane.
    card_width = min(plan.item_width, width)
    field = max(card_width - _BOX_OVERHEAD, 1)
    contents = [
        _feature_card("Currently Supported", _SUPPORTED, field),
        _feature_card("Not Yet Supported", _UNSUPPORTED, field),
    ]
    height = max(len(content) for content in contents)
    boxes = [
        render_box([*content, *([""] * (height - len(content)))], card_width, align="left")
        for content in contents
    ]
    if plan.stacked:
        stacked: list[str] = []
        for index, box in enumerate(boxes):
            if index:
                stacked.append("")
            stacked.extend(center_block(box, width))
        return stacked
    return center_block(join_horizontal(boxes, _FEATURE_GAP), width)


def _overview_cards(
    counts: dict[str, int], selected_index: int, width: int, bold: Callable[[str], str]
) -> list[str]:
    """Render the three navigable Database Overview cards.

    Mirrors :func:`home_renderer.render_home`'s card layout: the *selected_index*
    card is bolded, and the focused card is tagged as the selection (via
    :func:`blocks.card_row`) so the viewport keeps it on screen while scrolling.
    """
    plan = lay_out_row(
        len(OVERVIEW_CARDS),
        item_min=_STAT_CARD_MIN_WIDTH,
        item_ideal=_STAT_CARD_WIDTH,
        gap=_STAT_GAP,
        available=width,
    )
    cards: list[list[str]] = []
    for index, (key, title) in enumerate(OVERVIEW_CARDS):
        box = render_box([title, "", str(counts.get(key, 0))], plan.item_width, pad_y=2)
        if index == selected_index:
            box = [bold(line) for line in box]
        cards.append(box)
    return card_row(
        cards, width=width, gap=_STAT_GAP, selected_index=selected_index, stacked=plan.stacked
    )


def render_library_home(
    counts: dict[str, int],
    selected_index: int,
    *,
    width: int,
    bold: Callable[[str], str],
) -> list[str]:
    """Render the Library home page.

    Args:
        counts: Record counts keyed by subsection (``ncrm``/``materials``/
            ``counterions``); missing keys render as ``0``.
        selected_index: Index into :data:`OVERVIEW_CARDS` of the highlighted
            overview card; that card is rendered bold. A negative index
            highlights nothing.
        width: Current terminal width, used to size and centre every section.
        bold: Styler applied to the highlighted overview card.

    Returns:
        The composed home-page lines: a pinned title, the About paragraph and
        info cards, then the navigable Database Overview row.
    """
    inner = max(width - _SCREEN_INSET, 0)
    rule_width = section_width(width)

    # Only the title is pinned, so it stays visible while the guide scrolls.
    lines = tag_sticky([_TITLE, "─" * len(_TITLE)])

    lines += ["", section_rule("About This Tool", rule_width), ""]
    lines += textwrap.wrap(_ABOUT, width=max(inner, 1))

    lines += ["", section_rule("Capabilities", rule_width), ""]
    lines += _feature_cards(inner)

    lines += ["", section_rule("Database Overview", rule_width), ""]
    lines += _overview_cards(counts, selected_index, inner, bold)
    return lines
