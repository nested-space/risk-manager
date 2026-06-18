"""Landing-screen navigation: track entry, track isolation, and the quit modal.

The home screen is a landing menu whose three cards (``PROJECT``/``LIBRARY``/
``ADMIN``) are the only entry points to the top-level tracks. These tests cover
entering each track by hotkey and by Enter, the rule that descendants cannot jump
sideways into another track, and the Ctrl-C quit confirmation.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl.hotkeys import CTRL_B, CTRL_N, CTRL_P
from riskmanager_cli.repl.session_state import SessionState
from riskmanager_cli.repl_engine.list_navigator import ListItem
from riskmanager_cli.schema.create import (
    ManufacturingProcessCreate,
    MaterialCreate,
    ProjectCreate,
)


class _StubScreen:
    """Minimal screen stand-in exposing the ``width``/``bold``/``dim`` used by rendering."""

    width = 80
    output_height = 40

    @staticmethod
    def dim(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text

    @staticmethod
    def bold(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text

    @staticmethod
    def style_notice(message: str, level: str) -> str:
        """Return *message* unchanged (no terminal styling under test)."""
        del level
        return message


def _make_dispatcher(env: Environment) -> CommandDispatcher:
    """Build a dispatcher wired to a fresh context, session and stub screen."""
    return CommandDispatcher(ContextManager(), SessionState(), _StubScreen(), env)  # type: ignore[arg-type]


async def _push_route(dispatcher: CommandDispatcher, env: Environment) -> None:
    """Seed a project + process and push a route frame, leaving home behind."""
    material = await create_material(MaterialCreate(name="Caffeine"), env=env)
    assert material is not None
    project = await create_project(
        ProjectCreate(name="Alpha", therapy_area=TA.ONCOLOGY, material_id=UUID(str(material.id))),
        env=env,
    )
    assert project is not None
    process = await create_manufacturing_process(
        ManufacturingProcessCreate(
            project_id=UUID(str(project.id)), route_number=1, process_number=1
        ),
        env=env,
    )
    assert process is not None
    dispatcher.ctx.push(
        ContextFrame(
            track="route",
            project_id=str(project.id),
            process_id=str(process.id),
            route_label="1.1",
        )
    )


@pytest.mark.integration
async def test_home_project_hotkey_enters_project_select(temp_env: Environment) -> None:
    """Ctrl-P opens the project picker track."""
    dispatcher = _make_dispatcher(temp_env)
    await dispatcher.handle_hotkey(CTRL_P)
    assert dispatcher.ctx.current.track == "project_select"


@pytest.mark.integration
async def test_home_library_hotkey_enters_library_home(temp_env: Environment) -> None:
    """Ctrl-B opens the library home page (its select track), not a chooser prompt."""
    dispatcher = _make_dispatcher(temp_env)
    lines = await dispatcher.handle_hotkey(CTRL_B)
    assert dispatcher.prompt_state is None
    assert dispatcher.ctx.current.track == "library"
    assert dispatcher.ctx.current.library_sub == "select"
    assert any("Risk Manager Library" in line for line in lines)


@pytest.mark.integration
async def test_home_admin_hotkey_enters_admin(temp_env: Environment) -> None:
    """Ctrl-N opens the admin track."""
    dispatcher = _make_dispatcher(temp_env)
    await dispatcher.handle_hotkey(CTRL_N)
    assert dispatcher.ctx.current.track == "admin"


@pytest.mark.integration
async def test_home_enter_on_project_card_enters_project_select(temp_env: Environment) -> None:
    """Selecting the PROJECT card with Enter opens the project picker track."""
    dispatcher = _make_dispatcher(temp_env)
    await dispatcher.activate_list_selection(ListItem(label="P R O J E C T", item_id="project"))
    assert dispatcher.ctx.current.track == "project_select"


@pytest.mark.integration
async def test_home_enter_on_library_card_enters_library_home(temp_env: Environment) -> None:
    """Selecting the LIBRARY card with Enter opens the library home page."""
    dispatcher = _make_dispatcher(temp_env)
    lines = await dispatcher.activate_list_selection(
        ListItem(label="L I B R A R Y", item_id="library")
    )
    assert dispatcher.ctx.current.track == "library"
    assert dispatcher.ctx.current.library_sub == "select"
    assert any("Risk Manager Library" in line for line in lines)


@pytest.mark.integration
async def test_library_home_card_enter_opens_subsection(temp_env: Environment) -> None:
    """Enter on an overview card opens that subsection's table (the picker role)."""
    dispatcher = _make_dispatcher(temp_env)
    await dispatcher.handle_hotkey(CTRL_B)  # land on the library home

    selected = dispatcher.list_navigator.selected  # type: ignore[union-attr]  # first card: ncrm
    await dispatcher.activate_list_selection(selected)  # type: ignore[arg-type]

    assert dispatcher.ctx.current.track == "library"
    assert dispatcher.ctx.current.library_sub == "ncrm"


@pytest.mark.integration
async def test_library_command_accepted_from_home(temp_env: Environment) -> None:
    """`/library materials` from home enters the library track."""
    dispatcher = _make_dispatcher(temp_env)
    await dispatcher.dispatch("/library materials")
    assert dispatcher.ctx.current.track == "library"
    assert dispatcher.ctx.current.library_sub == "materials"


@pytest.mark.integration
async def test_library_command_rejected_from_descendant(temp_env: Environment) -> None:
    """`/library` cannot be reached from a descendant track (no sideways jumps)."""
    dispatcher = _make_dispatcher(temp_env)
    await _push_route(dispatcher, temp_env)

    result = await dispatcher.dispatch("/library materials")

    assert dispatcher.ctx.current.track == "route"
    assert any("Unknown command" in line for line in result)


@pytest.mark.integration
async def test_admin_command_rejected_from_descendant(temp_env: Environment) -> None:
    """`/admin` is refused from a descendant track with a pointer back home."""
    dispatcher = _make_dispatcher(temp_env)
    await _push_route(dispatcher, temp_env)

    result = await dispatcher.dispatch("/admin")

    assert dispatcher.ctx.current.track == "route"
    assert any("only available from home" in line for line in result)


@pytest.mark.integration
async def test_quit_confirm_sets_quit_requested_on_yes(temp_env: Environment) -> None:
    """Accepting the quit confirmation (default Yes) flags the loop to exit."""
    dispatcher = _make_dispatcher(temp_env)
    dispatcher.start_quit_confirm()

    await dispatcher.submit_prompt_selection()

    assert dispatcher.quit_requested is True


@pytest.mark.integration
async def test_quit_confirm_declined_stays_home(temp_env: Environment) -> None:
    """Choosing No leaves the dispatcher on home without requesting a quit."""
    dispatcher = _make_dispatcher(temp_env)
    dispatcher.start_quit_confirm()

    dispatcher.prompt_move("down")  # highlight "No"
    await dispatcher.submit_prompt_selection()

    assert dispatcher.quit_requested is False
    assert dispatcher.ctx.current.track == "home"
