"""Integration tests for the selectable library screen and inline edit flow.

These drive the :class:`CommandDispatcher` against a real (in-memory) SQLite
database to verify that the library subsections render as a navigable table, that
rows are alphabetised with alias counts, and that edit/delete act on the
caret-selected row (no chooser).
"""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.operations.counterion_operations import (
    add_counterion_alias,
    create_counterion,
    list_counterions,
)
from riskmanager_cli.repl.commands import CTRL_E, CTRL_X, CommandDispatcher
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl.session_state import SessionState
from riskmanager_cli.schema.create import CounterionAliasCreate, CounterionCreate


class _StubScreen:
    """Minimal screen stand-in exposing the width and styling used by rendering."""

    width = 80

    @staticmethod
    def dim(text: str) -> str:
        return text

    @staticmethod
    def bold(text: str) -> str:
        return text

    @staticmethod
    def style_notice(message: str, level: str) -> str:
        del level
        return message


def _library_dispatcher(env: Environment) -> CommandDispatcher:
    """Build a dispatcher already focused on the counterions subsection."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="library", library_sub="counterions"))
    return CommandDispatcher(ctx, SessionState(), _StubScreen(), env)  # type: ignore[arg-type]


async def _seed_counterions(env: Environment) -> None:
    chloride = await create_counterion(CounterionCreate(name="chloride"), env=env)
    await create_counterion(CounterionCreate(name="acetate"), env=env)
    assert chloride is not None
    await add_counterion_alias(
        CounterionAliasCreate(counterion_id=UUID(str(chloride.id)), alias="Cl-"), env=env
    )


@pytest.mark.integration
async def test_library_renders_navigable_table_alphabetically(temp_env: Environment) -> None:
    """The counterions screen renders a caret table sorted by name with counts."""
    await _seed_counterions(temp_env)
    dispatcher = _library_dispatcher(temp_env)

    lines = await dispatcher.render_current()

    # Navigator is active and selects the first (alphabetically first) row.
    assert dispatcher.list_navigator is not None
    assert dispatcher.list_navigator.selected is not None
    assert dispatcher.list_navigator.selected.label == "acetate"
    # Acetate sorts before chloride.
    acetate_at = next(i for i, line in enumerate(lines) if "acetate" in line)
    chloride_at = next(i for i, line in enumerate(lines) if "chloride" in line)
    assert acetate_at < chloride_at
    # The selected row carries the caret.
    assert any(line.startswith("> ") and "acetate" in line for line in lines)
    # Chloride's single alias is counted.
    assert any("chloride" in line and " 1 " in line for line in lines)


@pytest.mark.integration
async def test_library_ctrl_e_edits_selected_row(temp_env: Environment) -> None:
    """^E opens the edit form for the caret-selected row (no chooser)."""
    await _seed_counterions(temp_env)
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()

    # Move the caret to chloride, then edit it.
    dispatcher.list_navigator.move_down()  # type: ignore[union-attr]
    await dispatcher.handle_hotkey(CTRL_E)

    assert dispatcher.prompt_state is not None
    assert dispatcher.prompt_state.title == "Edit counterion"
    # The form is pre-filled with the selected row's name.
    assert dispatcher.prompt_state.fields[0].default == "chloride"


@pytest.mark.integration
async def test_library_ctrl_x_confirms_then_deletes_selected_row(temp_env: Environment) -> None:
    """^X confirms and deletes the caret-selected row."""
    await _seed_counterions(temp_env)
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()  # caret on acetate

    await dispatcher.handle_hotkey(CTRL_X)
    assert dispatcher.prompt_state is not None  # confirmation prompt
    await dispatcher.advance_prompt("yes")

    remaining = [ion.name for ion in await list_counterions(temp_env)]
    assert remaining == ["chloride"]


@pytest.mark.integration
async def test_library_ctrl_e_without_items_notifies(temp_env: Environment) -> None:
    """^E on an empty subsection reports nothing selected rather than erroring."""
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()

    await dispatcher.handle_hotkey(CTRL_E)

    assert dispatcher.take_notice() == ("No item selected.", "warning")
