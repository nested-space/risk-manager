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
    get_process_by_id,
)
from riskmanager_cli.operations.manufacturing_process_risk_operations import (
    list_risks_for_process,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import (
    create_project,
    get_project_by_id,
    list_projects,
)
from riskmanager_cli.operations.stage_operations import create_stage, list_stages_for_process
from riskmanager_cli.operations.stage_risk_operations import (
    create_stage_risk,
    list_risks_for_stage,
)
from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl.hotkeys import CTRL_A, CTRL_E, CTRL_F, CTRL_P, CTRL_R, CTRL_X
from riskmanager_cli.repl.session_state import SessionState
from riskmanager_cli.schema.create import (
    ManufacturingProcessCreate,
    MaterialCreate,
    ProjectCreate,
    StageCreate,
    StageRiskCreate,
)


class _StubScreen:
    """Minimal screen stand-in exposing the ``width`` and ``dim`` used by rendering."""

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
    def reverse(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text

    @staticmethod
    def style_notice(message: str, level: str) -> str:
        """Return *message* unchanged (no terminal styling under test)."""
        del level
        return message


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
async def test_project_select_add_hotkey_opens_project_prompt(temp_env: Environment) -> None:
    """Ctrl-P opens the project picker; Ctrl-A there starts the `/add project` flow."""
    await create_material(MaterialCreate(name="Caffeine"), env=temp_env)
    dispatcher = _make_dispatcher(temp_env)

    await dispatcher.handle_hotkey(CTRL_P)
    assert dispatcher.ctx.current.track == "project_select"

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
    assert any("─ Routes " in line for line in lines)
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


def _push_stage_focus(
    dispatcher: CommandDispatcher, project_id: str, process_id: str, stage_id: str
) -> None:
    dispatcher.ctx.push(
        ContextFrame(
            track="stage_focus",
            project_id=project_id,
            process_id=process_id,
            route_label="1.1",
            stage_id=stage_id,
            stage_name="Coupling",
        )
    )


def _push_risk_mode(
    dispatcher: CommandDispatcher,
    scope: str,
    *,
    project_id: str,
    process_id: str | None = None,
    stage_id: str | None = None,
) -> None:
    dispatcher.ctx.push(
        ContextFrame(
            track="risk_mode",
            project_id=project_id,
            process_id=process_id,
            route_label="1.1",
            stage_id=stage_id,
            risk_scope=scope,
        )
    )


@pytest.mark.integration
async def test_edit_form_prefills_text_then_blanks_select(temp_env: Environment) -> None:
    """An edit form exposes the entity's current value per field via prompt_prefill.

    Text fields surface their current value (so the loop can seed the editable
    buffer); select fields contribute nothing because their navigator pre-fills.
    """
    project_id, _ = await _seed_route(temp_env)
    dispatcher = _make_dispatcher(temp_env)
    dispatcher.ctx.push(ContextFrame(track="project", project_id=project_id, project_name="Alpha"))

    await dispatcher.handle_hotkey(CTRL_E)
    assert dispatcher.prompt_state is not None
    assert dispatcher.prompt_prefill() == "Alpha"  # name text field

    await dispatcher.advance_prompt("Renamed")
    assert dispatcher.prompt_prefill() == ""  # therapy_area is a select field

    await dispatcher.advance_prompt(TA.CVRM.value)
    updated = await get_project_by_id(UUID(project_id), env=temp_env)
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.therapy_area == TA.CVRM


@pytest.mark.integration
async def test_risk_mode_add_hotkey_creates_stage_risk(temp_env: Environment) -> None:
    """Ctrl-A in stage-scoped risk_mode opens the add-risk form and persists it."""
    project_id, process_id = await _seed_route(temp_env)
    stage = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Coupling", number=1), env=temp_env
    )
    assert stage is not None
    dispatcher = _make_dispatcher(temp_env)
    _push_risk_mode(
        dispatcher, "stage", project_id=project_id, process_id=process_id, stage_id=str(stage.id)
    )

    await dispatcher.handle_hotkey(CTRL_A)
    assert dispatcher.prompt_state is not None
    await dispatcher.advance_prompt("Threat")  # risk_type (Threat/Opportunity select)
    await dispatcher.advance_prompt("Exotherm")
    await dispatcher.advance_prompt("")  # description (optional)
    await dispatcher.advance_prompt("4")  # current_level (required select)
    await dispatcher.advance_prompt("Add cooling")  # proposed_mitigation (required)
    await dispatcher.advance_prompt("2")  # mitigated_level (required select)

    risks = await list_risks_for_stage(UUID(str(stage.id)), env=temp_env)
    assert [risk.name for risk in risks] == ["Exotherm"]
    assert (risks[0].current_level, risks[0].mitigated_level) == (4, 2)


@pytest.mark.integration
async def test_risk_mode_add_hotkey_creates_process_risk(temp_env: Environment) -> None:
    """Ctrl-A in process-scoped risk_mode persists a manufacturing-process risk."""
    project_id, process_id = await _seed_route(temp_env)
    dispatcher = _make_dispatcher(temp_env)
    _push_risk_mode(dispatcher, "process", project_id=project_id, process_id=process_id)

    await dispatcher.handle_hotkey(CTRL_A)
    assert dispatcher.prompt_state is not None
    await dispatcher.advance_prompt("Threat")  # risk_type (Threat/Opportunity select)
    await dispatcher.advance_prompt("Impurity carryover")
    await dispatcher.advance_prompt("")  # description (optional)
    await dispatcher.advance_prompt("Critical (5)")  # current_level (select by label)
    await dispatcher.advance_prompt("Inline assay")  # proposed_mitigation (required)
    await dispatcher.advance_prompt("3")  # mitigated_level (select by value)

    risks = await list_risks_for_process(UUID(process_id), env=temp_env)
    assert [risk.name for risk in risks] == ["Impurity carryover"]
    assert (risks[0].current_level, risks[0].mitigated_level) == (5, 3)


@pytest.mark.integration
async def test_risk_mode_add_hotkey_noop_for_project_scope(temp_env: Environment) -> None:
    """Ctrl-A is ignored in the project aggregate view (no single target entity)."""
    project_id, _ = await _seed_route(temp_env)
    dispatcher = _make_dispatcher(temp_env)
    _push_risk_mode(dispatcher, "project", project_id=project_id)

    result = await dispatcher.handle_hotkey(CTRL_A)
    assert result is None
    assert dispatcher.prompt_state is None


@pytest.mark.integration
async def test_risk_mode_edit_hotkey_prefills_and_updates_risk(temp_env: Environment) -> None:
    """Ctrl-E in risk_mode picks a risk, opens a pre-filled form, and saves edits."""
    project_id, process_id = await _seed_route(temp_env)
    stage = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Coupling", number=1), env=temp_env
    )
    assert stage is not None
    risk = await create_stage_risk(
        StageRiskCreate(
            stage_id=UUID(str(stage.id)),
            risk_type="Safety",
            name="Exotherm",
            current_level=5,
            proposed_mitigation="Add cooling",
            mitigated_level=2,
        ),
        env=temp_env,
    )
    assert risk is not None
    dispatcher = _make_dispatcher(temp_env)
    _push_risk_mode(
        dispatcher, "stage", project_id=project_id, process_id=process_id, stage_id=str(stage.id)
    )

    await dispatcher.handle_hotkey(CTRL_E)
    assert dispatcher.picker_state is not None
    await dispatcher.picker_select()

    assert dispatcher.prompt_state is not None
    # risk_type is now a Threat/Opportunity select; selects pre-fill via their
    # navigator, so the text prefill is empty even though the field is active.
    assert dispatcher.prompt_state.current_field.field_type == "select"
    assert dispatcher.prompt_prefill() == ""
    await dispatcher.advance_prompt("Opportunity")  # change risk_type via the select
    assert dispatcher.prompt_prefill() == "Exotherm"  # name pre-filled
    await dispatcher.advance_prompt("Runaway exotherm")  # change name
    for _ in range(4):
        await dispatcher.advance_prompt("")  # keep remaining defaults (incl. level selects)

    risks = await list_risks_for_stage(UUID(str(stage.id)), env=temp_env)
    assert len(risks) == 1
    assert risks[0].risk_type == "Opportunity"
    assert risks[0].name == "Runaway exotherm"
    # The level number-selects pre-select the stored values; empty submit keeps them.
    assert (risks[0].current_level, risks[0].mitigated_level) == (5, 2)


@pytest.mark.integration
async def test_stage_risks_hotkey_enters_stage_risk_mode(temp_env: Environment) -> None:
    """Ctrl-R on a focused stage opens the stage-scoped risk_mode view."""
    project_id, process_id = await _seed_route(temp_env)
    stage = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Coupling", number=1), env=temp_env
    )
    assert stage is not None
    dispatcher = _make_dispatcher(temp_env)
    _push_stage_focus(dispatcher, project_id, process_id, str(stage.id))

    await dispatcher.handle_hotkey(CTRL_R)
    assert dispatcher.ctx.current.track == "risk_mode"
    assert dispatcher.ctx.current.risk_scope == "stage"


@pytest.mark.integration
async def test_route_edit_chooser_updates_route_numbers(temp_env: Environment) -> None:
    """Ctrl-E → choose "route" → a pre-filled form updates route/process numbers."""
    project_id, process_id = await _seed_route(temp_env)
    dispatcher = _make_dispatcher(temp_env)
    _push_route(dispatcher, project_id, process_id)

    await dispatcher.handle_hotkey(CTRL_E)
    assert dispatcher.prompt_state is not None  # edit chooser
    await dispatcher.advance_prompt("route")

    assert dispatcher.prompt_state is not None  # route/process number form
    assert dispatcher.prompt_prefill() == "1"  # route_number pre-filled
    await dispatcher.advance_prompt("2")
    assert dispatcher.prompt_prefill() == "1"  # process_number pre-filled
    await dispatcher.advance_prompt("3")

    updated = await get_process_by_id(UUID(process_id), env=temp_env)
    assert updated is not None
    assert (updated.route_number, updated.process_number) == (2, 3)
