"""Application-agnostic terminal UI engine for the riskmanager REPL.

This package holds the generic TUI machinery — the event loop, terminal
drawing, viewport scrolling, list navigation, the guided-prompt/picker forms
engine, and the layout primitives. It has no dependency on the risk-manager
domain; an application drives it by implementing :class:`ReplController` and
calling :func:`start_repl`.

The names re-exported here are the engine's public surface. Import them from this
package (``from riskmanager_cli.repl_engine import ...``) rather than reaching
into individual submodules.
"""

from __future__ import annotations

from . import layout
from .controller import ReplController
from .forms import (
    FieldSpec,
    InfoSection,
    ModalController,
    PickerState,
    PromptState,
    field_key,
)
from .keys import is_backspace, is_enter, is_hotkey, is_scroll_key, is_text_input
from .list_navigator import ListItem, ListNavigator
from .loop import run_async, start_repl
from .screen import ScreenManager
from .viewport import (
    ViewModel,
    follow,
    max_offset,
    parse,
    selected_line,
    tag_selected,
    tag_sticky,
    window,
)

__all__ = [
    # entry point
    "start_repl",
    "run_async",
    # the application contract
    "ReplController",
    # terminal drawing
    "ScreenManager",
    # forms / modal engine
    "ModalController",
    "FieldSpec",
    "InfoSection",
    "PromptState",
    "PickerState",
    "field_key",
    # list navigation
    "ListItem",
    "ListNavigator",
    # viewport
    "ViewModel",
    "parse",
    "window",
    "follow",
    "max_offset",
    "selected_line",
    "tag_sticky",
    "tag_selected",
    # keystroke classification
    "is_enter",
    "is_backspace",
    "is_text_input",
    "is_hotkey",
    "is_scroll_key",
    # layout primitives (submodule)
    "layout",
]
