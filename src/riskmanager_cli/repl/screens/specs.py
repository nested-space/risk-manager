"""Per-screen capability + hint registry for the risk-manager REPL.

Each :class:`~...repl_engine.dispatch.ScreenSpec` declares what one screen offers
(navigation, search, tabs, and its Ctrl-hotkey actions); the engine derives the
footer and ``?`` legend from it. The registry is keyed by screen key (see
``CommandDispatcher.current_screen_key``), which splits the ``library`` track into
its landing page and list sub-modes. The matching screen's ``run_hotkey`` is the
source of truth the ``actions`` entries describe.

This data lives with the screens (not the dispatcher) so the :class:`AppScreen`
subclasses and the dispatcher's help/legend lookups share it without an import
cycle.
"""

from __future__ import annotations

from ...repl_engine import ScreenSpec

SCREEN_SPECS: dict[str, ScreenSpec] = {
    "home": ScreenSpec(True, False, ("^P project", "^B library", "^N admin"), back="^C quit"),
    "project_select": ScreenSpec(True, True, ("^A add project",)),
    "project": ScreenSpec(True, False, ("^T routes", "^R risks", "^A add process", "^E edit")),
    "route_select": ScreenSpec(True, True, ()),
    "route": ScreenSpec(
        False, True, ("^A add", "^F focus", "^E edit", "^X delete", "^L list", "^R risks")
    ),
    "stage_focus": ScreenSpec(
        True, False, ("^A add", "^L list", "^E edit", "^R risks", "^U unassign", "^X delete")
    ),
    "component_focus": ScreenSpec(
        True, False, ("^A assign salt", "^E edit", "^U unassign", "^X delete", "^R risks")
    ),
    "library_home": ScreenSpec(True, False, (), tab_hint="Tab switch tabs"),
    "library_list": ScreenSpec(
        True, True, ("^E edit", "^A add", "^X delete", "^F filter", "^K structure")
    ),
    "library_detail": ScreenSpec(False, False, ("^E edit", "^K structure")),
    "admin": ScreenSpec(False, False, ("^A action",)),
    "risk_mode": ScreenSpec(False, False, ("^A add", "^E edit", "^L refresh")),
}

#: Fallback for an unknown screen key: no capabilities, just a way back.
DEFAULT_SPEC = ScreenSpec(False, False, ())
