"""Tests for the ``^K`` show-structure hotkey on molecule-bearing screens.

Every screen that displays a molecule (the library screens plus the component- and
stage-focus screens) shares :meth:`AppScreen.show_structure_notice`. These tests
drive :meth:`CommandDispatcher.handle_hotkey` with ``^K`` and assert the resulting
notice, patching ``show_structure`` so no image viewer is launched.
"""

from collections.abc import Callable
from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA, NcrmRole
from riskmanager_cli.operations.component_operations import create_component
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.ncrm_library_operations import create_ncrm_library_entry
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.operations.stage_component_operations import create_stage_component
from riskmanager_cli.operations.stage_ncrm_operations import create_stage_ncrm
from riskmanager_cli.operations.stage_operations import create_stage
from riskmanager_cli.repl import screens
from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl.hotkeys import CTRL_K
from riskmanager_cli.repl.session_state import SessionState
from riskmanager_cli.schema.create import (
    ComponentCreate,
    ManufacturingProcessCreate,
    MaterialCreate,
    NcrmLibraryCreate,
    ProjectCreate,
    StageComponentCreate,
    StageCreate,
    StageNcrmCreate,
)
from riskmanager_cli.service.structure_viewer import StructureResult


class _StubScreen:
    """Minimal screen stand-in exposing the surface the renderers touch."""

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


@pytest.fixture
def patch_show_structure(monkeypatch: pytest.MonkeyPatch) -> Callable[[StructureResult], list[str]]:
    """Patch ``base.show_structure`` and record the SMILES it was called with."""

    def install(result: StructureResult) -> list[str]:
        calls: list[str] = []

        def fake_show_structure(smiles: str, **_: object) -> StructureResult:
            calls.append(smiles)
            return result

        monkeypatch.setattr(screens.base, "show_structure", fake_show_structure)
        return calls

    return install


async def _seed_component(env: Environment, *, smiles: str | None) -> tuple[str, str]:
    """Seed a project/process/material/component and return process and component ids."""
    material = await create_material(MaterialCreate(name="Caffeine", smiles=smiles), env=env)
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
    component = await create_component(
        ComponentCreate(process_id=UUID(str(process.id)), material_id=UUID(str(material.id))),
        env=env,
    )
    assert component is not None
    return str(process.id), str(component.id)


def _push_component_focus(dispatcher: CommandDispatcher, component_id: str) -> None:
    dispatcher.ctx.push(
        ContextFrame(
            track="component_focus",
            component_id=component_id,
            component_name="Caffeine",
        )
    )


def _push_stage_focus(dispatcher: CommandDispatcher, process_id: str, stage_id: str) -> None:
    dispatcher.ctx.push(
        ContextFrame(
            track="stage_focus",
            process_id=process_id,
            route_label="1.1",
            stage_id=stage_id,
            stage_name="Coupling",
        )
    )


@pytest.mark.integration
async def test_component_focus_structure_hotkey_opens_viewer(
    temp_env: Environment,
    patch_show_structure: Callable[[StructureResult], list[str]],
) -> None:
    """^K on a component whose material has a SMILES renders and opens it."""
    calls = patch_show_structure(StructureResult.OK)
    _, component_id = await _seed_component(temp_env, smiles="CCO")
    dispatcher = _make_dispatcher(temp_env)
    _push_component_focus(dispatcher, component_id)

    await dispatcher.handle_hotkey(CTRL_K)

    assert calls == ["CCO"]
    assert dispatcher.take_notice() == ("Opened structure for 'Caffeine'.", "success")


@pytest.mark.integration
async def test_component_focus_structure_hotkey_warns_without_smiles(
    temp_env: Environment,
    patch_show_structure: Callable[[StructureResult], list[str]],
) -> None:
    """^K on a component whose material has no SMILES warns and never renders."""
    calls = patch_show_structure(StructureResult.OK)
    _, component_id = await _seed_component(temp_env, smiles=None)
    dispatcher = _make_dispatcher(temp_env)
    _push_component_focus(dispatcher, component_id)

    await dispatcher.handle_hotkey(CTRL_K)

    assert calls == []
    assert dispatcher.take_notice() == ("No SMILES available for 'Caffeine'.", "warning")


@pytest.mark.integration
async def test_stage_focus_structure_hotkey_resolves_component_row(
    temp_env: Environment,
    patch_show_structure: Callable[[StructureResult], list[str]],
) -> None:
    """^K on a stage's component row resolves the material's SMILES and opens it."""
    calls = patch_show_structure(StructureResult.OK)
    process_id, component_id = await _seed_component(temp_env, smiles="CCO")
    stage = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Coupling", number=1), env=temp_env
    )
    assert stage is not None
    await create_stage_component(
        StageComponentCreate(
            stage_id=UUID(str(stage.id)),
            component_id=UUID(component_id),
            component_type="reactant",
        ),
        env=temp_env,
    )
    dispatcher = _make_dispatcher(temp_env)
    _push_stage_focus(dispatcher, process_id, str(stage.id))

    await dispatcher.render_current()  # populate the caret navigator
    await dispatcher.handle_hotkey(CTRL_K)

    assert calls == ["CCO"]
    assert dispatcher.take_notice() == ("Opened structure for 'Caffeine'.", "success")


@pytest.mark.integration
async def test_stage_focus_structure_hotkey_resolves_ncrm_row(
    temp_env: Environment,
    patch_show_structure: Callable[[StructureResult], list[str]],
) -> None:
    """^K on a stage's NCRM row resolves the library entry's SMILES and opens it."""
    calls = patch_show_structure(StructureResult.OK)
    process_id, _ = await _seed_component(temp_env, smiles="CCO")
    stage = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Coupling", number=1), env=temp_env
    )
    assert stage is not None
    ncrm = await create_ncrm_library_entry(
        NcrmLibraryCreate(name="Palladium", smiles="[Pd]"), env=temp_env
    )
    assert ncrm is not None
    await create_stage_ncrm(
        StageNcrmCreate(
            ncrm_id=UUID(str(ncrm.id)), stage_id=UUID(str(stage.id)), role=NcrmRole.CATALYST
        ),
        env=temp_env,
    )
    dispatcher = _make_dispatcher(temp_env)
    _push_stage_focus(dispatcher, process_id, str(stage.id))

    # The stage has no linked components, so its single NCRM row is the default
    # caret target after the navigator is built.
    await dispatcher.render_current()
    await dispatcher.handle_hotkey(CTRL_K)

    assert calls == ["[Pd]"]
    assert dispatcher.take_notice() == ("Opened structure for 'Palladium'.", "success")


@pytest.mark.integration
async def test_stage_focus_structure_hotkey_warns_on_non_molecule_row(
    temp_env: Environment,
    patch_show_structure: Callable[[StructureResult], list[str]],
) -> None:
    """^K with no caret selection (empty stage) warns instead of rendering."""
    calls = patch_show_structure(StructureResult.OK)
    process_id, _ = await _seed_component(temp_env, smiles="CCO")
    stage = await create_stage(
        StageCreate(process_id=UUID(process_id), name="Coupling", number=1), env=temp_env
    )
    assert stage is not None
    dispatcher = _make_dispatcher(temp_env)
    _push_stage_focus(dispatcher, process_id, str(stage.id))

    await dispatcher.render_current()
    await dispatcher.handle_hotkey(CTRL_K)

    assert calls == []
    assert dispatcher.take_notice() == ("No molecule selected.", "warning")
