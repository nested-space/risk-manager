"""Tests for the Ctrl-key hotkey layer that replaces typed slash commands.

These drive :meth:`CommandDispatcher.handle_hotkey` to verify that hotkeys open
the same prompt/picker/chooser flows the slash commands used to, and that the
new chooser → picker → form chains reach the existing leaf handlers. Select
fields (including choosers and confirmations) are advanced with
``advance_prompt`` because ``submit_value`` resolves the option by value.
"""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project, list_projects
from riskmanager_cli.operations.stage_operations import create_stage, list_stages_for_process
from riskmanager_cli.repl.commands import (
    CTRL_A,
    CTRL_F,
    CTRL_R,
    CTRL_X,
    CommandDispatcher,
)
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl.session_state import SessionState
from riskmanager_cli.schema.create import (
    ManufacturingProcessCreate,
    MaterialCreate,
    ProjectCreate,
    StageCreate,
)


class _StubScreen:
    """Minimal screen stand-in exposing the ``width`` and ``dim`` used by rendering."""

    width = 80

    @staticmethod
    def dim(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text


def _make_dispatcher(env: Environment) -> CommandDispatcher:
    """Build a dispatcher wired to a fresh context, session and stub screen."""
    screen = _StubScreen()
    return CommandDispatcher(ContextManager(), SessionState(), screen, env)  # type: ignore[arg-type]


async def _seed_route(env: Environment) -> tuple[str, str]:
    """Create a project + manufacturing process and return their string ids."""
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
    return str(project.id), str(process.id)


def _push_route(dispatcher: CommandDispatcher, project_id: str, process_id: str) -> None:
    dispatcher.ctx.push(
        ContextFrame(
            track="route",
            project_id=project_id,
            process_id=process_id,
            route_label="1.1",
        )
    )


@pytest.mark.integration
async def test_home_add_hotkey_opens_project_prompt(temp_env: Environment) -> None:
    """Ctrl-A on home starts the `/add project` guided prompt + material picker."""
    await create_material(MaterialCreate(name="Caffeine"), env=temp_env)
    dispatcher = _make_dispatcher(temp_env)

    await dispatcher.handle_hotkey(CTRL_A)
    assert dispatcher.prompt_state is not None

    await dispatcher.advance_prompt("AlphaProject")
    await dispatcher.advance_prompt(TA.ONCOLOGY.value)
    assert dispatcher.picker_state is not None

    dispatcher.update_picker_query("caf")
    await dispatcher.picker_select()
    assert [project.name for project in await list_projects(env=temp_env)] == ["AlphaProject"]


@pytest.mark.integration
async def test_unknown_hotkey_returns_none(temp_env: Environment) -> None:
    """An unmapped control character is ignored (no action, no modal)."""
    dispatcher = _make_dispatcher(temp_env)
    result = await dispatcher.handle_hotkey("\x15")  # Ctrl-U: unmapped on home
    assert result is None
    assert dispatcher.prompt_state is None
    assert dispatcher.picker_state is None


@pytest.mark.integration
async def test_route_add_chooser_creates_stage(temp_env: Environment) -> None:
    """Ctrl-A → choose "stage" → name/number form persists a stage."""
    project_id, process_id = await _seed_route(temp_env)
    dispatcher = _make_dispatcher(temp_env)
    _push_route(dispatcher, project_id, process_id)

    await dispatcher.handle_hotkey(CTRL_A)
    assert dispatcher.prompt_state is not None  # the add chooser
    await dispatcher.advance_prompt("stage")  # pick the "stage" variant

    assert dispatcher.prompt_state is not None  # name + number form
    await dispatcher.advance_prompt("Coupling")
    await dispatcher.advance_prompt("1")

    assert dispatcher.take_notice() == ("Created stage 'Coupling'.", "success")
    stages = await list_stages_for_process(UUID(process_id), env=temp_env)
    assert [stage.name for stage in stages] == ["Coupling"]


@pytest.mark.integration
async def test_route_focus_chooser_drills_into_stage(temp_env: Environment) -> None:
    """Ctrl-F → choose "stage" → pick a stage drills into the stage_focus track."""
    project_id, process_id = await _seed_route(temp_env)
    await create_stage(
        StageCreate(process_id=UUID(process_id), name="Coupling", number=1), env=temp_env
    )
    dispatcher = _make_dispatcher(temp_env)
    _push_route(dispatcher, project_id, process_id)

    await dispatcher.handle_hotkey(CTRL_F)
    await dispatcher.advance_prompt("stage")  # → stage picker
    assert dispatcher.picker_state is not None

    dispatcher.update_picker_query("coup")
    await dispatcher.picker_select()
    assert dispatcher.ctx.current.track == "stage_focus"


@pytest.mark.integration
async def test_stage_delete_hotkey_confirms_then_deletes(temp_env: Environment) -> None:
    """Ctrl-X on a focused stage opens a confirm prompt; "yes" deletes the stage."""
    project_id, process_id = await _seed_route(temp_env)
    stage = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Coupling", number=1), env=temp_env
    )
    assert stage is not None
    dispatcher = _make_dispatcher(temp_env)
    _push_route(dispatcher, project_id, process_id)
    dispatcher.ctx.push(
        ContextFrame(
            track="stage_focus",
            project_id=project_id,
            process_id=process_id,
            stage_id=str(stage.id),
            stage_name="Coupling",
        )
    )

    await dispatcher.handle_hotkey(CTRL_X)
    assert dispatcher.prompt_state is not None  # confirmation prompt
    await dispatcher.advance_prompt("yes")

    assert dispatcher.take_notice() == ("Stage deleted.", "success")
    assert await list_stages_for_process(UUID(process_id), env=temp_env) == []
    assert dispatcher.ctx.current.track == "route"  # popped back to the route


@pytest.mark.integration
async def test_project_screen_lists_routes_and_opens_selection(temp_env: Environment) -> None:
    """The project screen renders a navigable routes pick-list; Enter opens one."""
    material = await create_material(MaterialCreate(name="Caffeine"), env=temp_env)
    assert material is not None
    project = await create_project(
        ProjectCreate(name="Alpha", therapy_area=TA.ONCOLOGY, material_id=UUID(str(material.id))),
        env=temp_env,
    )
    assert project is not None
    for route_number, process_number in [(1, 1), (1, 2)]:
        await create_manufacturing_process(
            ManufacturingProcessCreate(
                project_id=UUID(str(project.id)),
                route_number=route_number,
                process_number=process_number,
            ),
            env=temp_env,
        )

    dispatcher = _make_dispatcher(temp_env)
    dispatcher.ctx.push(
        ContextFrame(track="project", project_id=str(project.id), project_name="Alpha")
    )

    lines = await dispatcher.render_current()
    assert "Routes / processes:" in lines
    assert any("Route 1 Process 1" in line for line in lines)
    assert dispatcher.list_navigator is not None

    selected = dispatcher.list_navigator.selected
    assert selected is not None
    await dispatcher.activate_list_selection(selected)
    assert dispatcher.ctx.current.track == "route"


@pytest.mark.integration
async def test_no_arg_hotkey_reuses_slash_handler(temp_env: Environment) -> None:
    """Ctrl-R on a route opens the same risk view as `/risks` (risk_mode track)."""
    project_id, process_id = await _seed_route(temp_env)
    dispatcher = _make_dispatcher(temp_env)
    _push_route(dispatcher, project_id, process_id)

    await dispatcher.handle_hotkey(CTRL_R)
    assert dispatcher.ctx.current.track == "risk_mode"
