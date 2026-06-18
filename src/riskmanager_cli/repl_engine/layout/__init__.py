"""Layout engine: the REPL's single, well-organised area for visual composition.

This package owns every layout concern, in strict low→high dependency order so
there are no cycles:

* :mod:`geometry` — ANSI-aware width measurement and 2-D padding, plus the
  ``HAlign``/``VAlign`` vocabulary and the ``Block`` alias every module shares.
* :mod:`responsive` — pure layout *decisions* (column fitting, card row-vs-stack).
* :mod:`stacks` — vertical/horizontal stacking containers and the card row.
* :mod:`overlay` — the StackPane: composite blocks onto one fixed region.
* :mod:`frame` — the unicode box widget.
* :mod:`table` — section rules and box-drawn tables.
* :mod:`widgets` — content widgets (title, subtitle, text area, card).
* :mod:`tabpane` — the box-drawn tab container.

Screen renderers import from this package rather than the individual modules, so
the geometry lives in exactly one place.
"""

from __future__ import annotations

from .frame import render_box
from .geometry import Block, HAlign, VAlign, block_width, pad_block, pad_line, visible_len
from .overlay import Placement, overlay
from .responsive import RowPlan, fit_widths, lay_out_row, select_columns, widest_fitting
from .stacks import card_row, center_block, hstack, join_horizontal, vstack
from .table import Column, render_table, section_rule, section_width
from .tabpane import tabpane
from .widgets import bullet_list, card, subtitle, text_area, title

__all__ = [
    "Block",
    "Column",
    "HAlign",
    "Placement",
    "RowPlan",
    "VAlign",
    "block_width",
    "bullet_list",
    "card",
    "card_row",
    "center_block",
    "fit_widths",
    "hstack",
    "join_horizontal",
    "lay_out_row",
    "overlay",
    "pad_block",
    "pad_line",
    "render_box",
    "render_table",
    "section_rule",
    "section_width",
    "select_columns",
    "subtitle",
    "tabpane",
    "text_area",
    "title",
    "vstack",
    "visible_len",
    "widest_fitting",
]
