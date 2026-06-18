"""First-run database bootstrap: create + seed with a live progress screen.

Detects a brand-new install (no database file at the resolved path) and, when
found, creates the schema and seeds the default counterion and NCRM reference
libraries while rendering an in-place progress box::

    ┌──────────────────────────────────────────────┐
    │  No database detected. Initialising:         │
    │  - Creating database ..................... ✓ │
    │  - Seeding NCRM library (325/325) ........ ✓ │
    │  - Seeding counterion library (12/24) ...    │
    └──────────────────────────────────────────────┘

Why this lives outside the REPL loop:
    This runs once at startup, before the REPL enters fullscreen and before a
    :class:`~riskmanager_cli.repl.screen.ScreenManager` exists. It therefore
    writes to the normal screen via ``sys.stdout`` directly — the same
    startup-phase pattern :mod:`~riskmanager_cli.__main__` uses for terminal
    setup/teardown — rather than routing through ``ScreenManager``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import blessed

from ..config.settings import Environment, build_db_url, get_db_path
from ..database.db_session import init_db
from ..operations.seed_operations import (
    COUNTERION_SEED_FILE,
    EXAMPLE_PROJECT_SEED_FILES,
    NCRM_SEED_FILE,
    load_example_project,
    load_seed_entries,
    seed_counterions,
    seed_example_project,
    seed_ncrm,
)
from ..repl_engine.layout import render_box

_CONTENT_WIDTH = 46
_BOX_WIDTH = _CONTENT_WIDTH + 6  # + 2 borders + 2*pad_x (pad_x defaults to 2)


def is_first_run(env: Environment) -> bool:
    """Return ``True`` when no database file exists yet for *env*.

    In-memory databases (``:memory:``) never count as first run — they have no
    file and are used only by tests.

    Args:
        env: Active database environment.

    Returns:
        ``True`` if the resolved database file is absent (a genuine first run).
    """
    path = get_db_path(env)
    return path is not None and not path.exists()


@dataclass
class _Step:
    """Mutable state for one row of the bootstrap progress box."""

    title: str
    total: int = 0
    done: int = 0
    complete: bool = False


class _BootstrapScreen:
    """Renders the initialisation box and redraws it in place as steps advance."""

    def __init__(self, term: blessed.Terminal) -> None:
        """Store the terminal and define the fixed list of bootstrap steps.

        Args:
            term: Active blessed terminal for styling and cursor movement.
        """
        self._term = term
        self._steps = [
            _Step("Creating database"),
            _Step("Seeding NCRM library"),
            _Step("Seeding counterion library"),
            _Step("Seeding example project entities"),
        ]
        self._rendered_lines = 0

    def begin(self, index: int, total: int) -> None:
        """Mark step *index* as running with *total* expected rows and redraw."""
        self._steps[index].total = total
        self._render()

    def advance(self, index: int, done: int) -> None:
        """Update the running count for step *index*, throttling redraws.

        Args:
            index: Step to update.
            done: Number of rows processed so far.
        """
        step = self._steps[index]
        step.done = done
        # Cap redraws to roughly 50 frames per step to avoid flicker on large seeds.
        stride = max(1, step.total // 50)
        if done == step.total or done % stride == 0:
            self._render()

    def complete(self, index: int) -> None:
        """Mark step *index* as finished and redraw with a check mark."""
        step = self._steps[index]
        step.complete = True
        step.done = step.total
        self._render()

    def _format_step(self, step: _Step) -> str:
        """Build one fixed-width step line with a dotted leader and status token."""
        prefix = f"  - {step.title} "
        if step.complete:
            status = "✓"
        elif step.total:
            status = f"({step.done}/{step.total})"
        else:
            status = ""
        trailing = f" {status}" if status else ""
        dots = max(0, _CONTENT_WIDTH - len(prefix) - len(trailing))
        line = f"{prefix}{'.' * dots}{trailing}"
        if step.complete:
            line = line.replace("✓", self._term.green("✓"))
        return line

    def _render(self) -> None:
        """Draw (or redraw in place) the full progress box on the normal screen."""
        content = ["No database detected. Initialising:", ""]
        content += [self._format_step(step) for step in self._steps]
        box = render_box(content, _BOX_WIDTH, align="left")

        out = sys.stdout
        if self._rendered_lines:
            out.write(self._term.move_up(self._rendered_lines))
        for line in box:
            out.write(f"\r{self._term.clear_eol}{line}\n")
        out.flush()
        self._rendered_lines = len(box)


async def run_first_time_setup(term: blessed.Terminal, env: Environment) -> None:
    """Create and seed a new database, rendering a live progress box.

    Intended to be invoked (via ``asyncio.run``) from the entry point only when
    :func:`is_first_run` is ``True``. Creates the schema, then seeds the NCRM and
    counterion libraries from the committed JSON seed files, updating the box
    after each step.

    Args:
        term: Active blessed terminal for the progress display.
        env: Active database environment.
    """
    screen = _BootstrapScreen(term)
    # total=0 keeps this step countless — it shows a dotted leader then a check
    # mark, since a running "(0/1)" reads oddly for a single schema-creation step.
    screen.begin(0, total=0)
    await init_db(build_db_url(env))
    screen.complete(0)

    ncrm_entries = load_seed_entries(NCRM_SEED_FILE)
    screen.begin(1, total=len(ncrm_entries))
    await seed_ncrm(ncrm_entries, env, progress=lambda done, _total: screen.advance(1, done))
    screen.complete(1)

    counterion_entries = load_seed_entries(COUNTERION_SEED_FILE)
    screen.begin(2, total=len(counterion_entries))
    await seed_counterions(
        counterion_entries, env, progress=lambda done, _total: screen.advance(2, done)
    )
    screen.complete(2)

    # Seeded last because their stages reference entries in the NCRM library above.
    # Both example projects share one progress line whose counter aggregates the
    # entities (materials + stages) of every project; ``base`` carries the count
    # already completed by earlier projects so the line keeps climbing.
    seeds = [load_example_project(name) for name in EXAMPLE_PROJECT_SEED_FILES]
    screen.begin(3, total=sum(len(s["materials"]) + len(s["stages"]) for s in seeds))
    base = 0

    def advance_projects(step: int, _total: int) -> None:
        screen.advance(3, base + step)

    for seed in seeds:
        await seed_example_project(seed, env, progress=advance_projects)
        base += len(seed["materials"]) + len(seed["stages"])
    screen.complete(3)
