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
from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl.hotkeys import CTRL_E, CTRL_K, CTRL_O, CTRL_X
from riskmanager_cli.repl.session_state import SessionState
from riskmanager_cli.schema.create import CounterionAliasCreate, CounterionCreate
from riskmanager_cli.service.structure_viewer import StructureResult


class _StubScreen:
    """Minimal screen stand-in exposing the width and styling used by rendering."""

    width = 80
    output_height = 40

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


@pytest.mark.integration
async def test_library_ctrl_k_without_selection_notifies(temp_env: Environment) -> None:
    """^K on an empty subsection reports nothing selected rather than erroring."""
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()

    await dispatcher.handle_hotkey(CTRL_K)

    assert dispatcher.take_notice() == ("No item selected.", "warning")


@pytest.mark.integration
async def test_library_ctrl_k_without_smiles_notifies(temp_env: Environment) -> None:
    """^K on a row without a SMILES string names the entity in the warning."""
    await _seed_counterions(temp_env)  # acetate (no SMILES) sorts first
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()

    await dispatcher.handle_hotkey(CTRL_K)

    assert dispatcher.take_notice() == ("No SMILES available for 'acetate'.", "warning")


@pytest.mark.integration
async def test_library_ctrl_k_opens_structure(
    temp_env: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """^K on a row with a SMILES renders/opens it and reports success."""
    await create_counterion(CounterionCreate(name="acetate", smiles="CC(=O)[O-]"), env=temp_env)
    seen: list[str] = []
    monkeypatch.setattr(
        "riskmanager_cli.repl.screens.library.show_structure",
        lambda smiles, **_kw: seen.append(smiles) or StructureResult.OK,
    )
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()

    await dispatcher.handle_hotkey(CTRL_K)

    assert seen == ["CC(=O)[O-]"]
    assert dispatcher.take_notice() == ("Opened structure for 'acetate'.", "success")


@pytest.mark.integration
async def test_library_detail_ctrl_k_opens_structure(
    temp_env: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """^K works on the detail screen, acting on the shown entry's SMILES."""
    await create_counterion(CounterionCreate(name="acetate", smiles="CC(=O)[O-]"), env=temp_env)
    monkeypatch.setattr(
        "riskmanager_cli.repl.screens.library.show_structure",
        lambda _smiles, **_kw: StructureResult.OK,
    )
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()
    selected = dispatcher.list_navigator.selected  # type: ignore[union-attr]
    await dispatcher.activate_list_selection(selected)  # type: ignore[arg-type]
    assert dispatcher.ctx.current.track == "library_detail"

    await dispatcher.handle_hotkey(CTRL_K)

    assert dispatcher.take_notice() == ("Opened structure for 'acetate'.", "success")


@pytest.mark.integration
async def test_library_enter_shows_detail_with_all_aliases(temp_env: Environment) -> None:
    """Enter opens the detail screen on a library_detail frame, listing aliases."""
    await _seed_counterions(temp_env)
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()

    dispatcher.list_navigator.move_down()  # type: ignore[union-attr]  # chloride (has alias Cl-)
    selected = dispatcher.list_navigator.selected  # type: ignore[union-attr]
    lines = await dispatcher.activate_list_selection(selected)  # type: ignore[arg-type]

    assert dispatcher.ctx.current.track == "library_detail"
    assert dispatcher.ctx.current.library_detail_id == selected.item_id  # type: ignore[union-attr]
    assert lines[0] == "chloride"
    assert any("Aliases (1)" in line for line in lines)
    assert any("• Cl-" in line for line in lines)
    # The detail page is not a list screen, so the navigator is cleared.
    assert dispatcher.list_navigator is None


@pytest.mark.integration
async def test_library_detail_back_returns_to_list_not_home(temp_env: Environment) -> None:
    """Leaving the detail screen pops to the library list, not all the way home."""
    await _seed_counterions(temp_env)
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()
    selected = dispatcher.list_navigator.selected  # type: ignore[union-attr]
    await dispatcher.activate_list_selection(selected)  # type: ignore[arg-type]

    popped = dispatcher.ctx.pop()  # what ^C does in the loop

    assert popped is not None
    assert dispatcher.ctx.current.track == "library"
    lines = await dispatcher.render_current()
    assert any(line.startswith("> ") and "acetate" in line for line in lines)


@pytest.mark.integration
async def test_library_detail_ctrl_e_opens_edit_form(temp_env: Environment) -> None:
    """^E on the detail screen opens the edit form for the shown entry."""
    await _seed_counterions(temp_env)
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()
    selected = dispatcher.list_navigator.selected  # type: ignore[union-attr]  # acetate
    await dispatcher.activate_list_selection(selected)  # type: ignore[arg-type]

    await dispatcher.handle_hotkey(CTRL_E)

    assert dispatcher.prompt_state is not None
    assert dispatcher.prompt_state.title == "Edit counterion"
    assert dispatcher.prompt_state.fields[0].default == "acetate"


@pytest.mark.integration
async def test_library_ctrl_o_is_no_longer_bound(temp_env: Environment) -> None:
    """^O does nothing on the library list (Enter now owns 'show')."""
    await _seed_counterions(temp_env)
    dispatcher = _library_dispatcher(temp_env)
    await dispatcher.render_current()

    assert await dispatcher.handle_hotkey(CTRL_O) is None


def _library_home_dispatcher(env: Environment) -> CommandDispatcher:
    """Build a dispatcher on the Library home (the tabbed landing page)."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="library", library_sub="select"))
    return CommandDispatcher(ctx, SessionState(), _StubScreen(), env)  # type: ignore[arg-type]


@pytest.mark.integration
async def test_library_home_tab_toggles_content_and_navigability(temp_env: Environment) -> None:
    """Tab switches the home pane between the navigable Libraries and Information tabs."""
    dispatcher = _library_home_dispatcher(temp_env)
    assert dispatcher.tab_count() == 2

    # Libraries tab: navigable cards, with a live navigator.
    libraries = "\n".join(await dispatcher.render_current())
    assert dispatcher.active_tab() == 0
    assert dispatcher.is_navigable()
    assert dispatcher.list_navigator is not None
    assert "Libraries" in libraries and "Information" in libraries

    # Tab → Information: capability cards, not navigable, no navigator.
    dispatcher.cycle_active_tab(1)
    information = "\n".join(await dispatcher.render_current())
    assert dispatcher.active_tab() == 1
    assert not dispatcher.is_navigable()
    assert dispatcher.list_navigator is None
    assert "Currently Supported" in information

    # Tab wraps back to the Libraries tab.
    dispatcher.cycle_active_tab(1)
    assert dispatcher.active_tab() == 0


@pytest.mark.integration
async def test_library_home_active_tab_resets_on_navigation(temp_env: Environment) -> None:
    """Leaving the Library home resets its active tab to the first."""
    dispatcher = _library_home_dispatcher(temp_env)
    dispatcher.cycle_active_tab(1)
    assert dispatcher.active_tab() == 1

    # Navigating into a subsection changes the screen key; the tab resets.
    dispatcher.ctx.current.library_sub = "counterions"
    assert dispatcher.active_tab() == 0
