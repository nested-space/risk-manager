"""Integration tests for caret navigation on the Stage Focus page.

Drive :meth:`CommandDispatcher.activate_list_selection` end-to-end to verify that
selecting a stage row jumps to the right destination: a component opens the
component-focus screen (pushed onto the stage frame, so back returns to the
stage), while NCRMs and risks open inline edit forms that persist via their
update operations.
"""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA, NcrmRole
from riskmanager_cli.model.tables import Stage
from riskmanager_cli.operations.component_operations import create_component
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.ncrm_library_operations import create_ncrm_library_entry
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.operations.stage_component_operations import create_stage_component
from riskmanager_cli.operations.stage_ncrm_operations import (
    create_stage_ncrm,
    list_ncrms_for_stage,
)
from riskmanager_cli.operations.stage_operations import create_stage
from riskmanager_cli.operations.stage_risk_operations import (
    create_stage_risk,
    list_risks_for_stage,
)
from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl.list_navigator import ListItem
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
    StageRiskCreate,
)


class _StubScreen:
    """Minimal screen stand-in exposing the ``width`` and styling used by rendering."""

    width = 80

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


class _Seed:
    """Identifiers for the seeded stage and its linked rows."""

    def __init__(self, stage: Stage, component_id: str, ncrm_link_id: str, risk_id: str) -> None:
        self.stage = stage
        self.component_id = component_id
        self.ncrm_link_id = ncrm_link_id
        self.risk_id = risk_id


async def _seed(env: Environment) -> _Seed:
    """Create a project → process → stage with one component, NCRM, and risk."""
    material = await create_material(MaterialCreate(name="Caffeine"), env=env)
    assert material is not None
    project = await create_project(
        ProjectCreate(name="Proj", therapy_area=TA.ONCOLOGY, material_id=UUID(str(material.id))),
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
    stage = await create_stage(
        StageCreate(process_id=UUID(str(process.id)), name="Reaction", number=1), env=env
    )
    assert stage is not None

    component = await create_component(
        ComponentCreate(process_id=UUID(str(process.id)), material_id=UUID(str(material.id))),
        env=env,
    )
    assert component is not None
    link = await create_stage_component(
        StageComponentCreate(
            stage_id=UUID(str(stage.id)),
            component_id=UUID(str(component.id)),
            component_type="reactant",
        ),
        env=env,
    )
    assert link is not None

    ncrm = await create_ncrm_library_entry(
        NcrmLibraryCreate(display_name="methanol", common_name="methanol"), env=env
    )
    assert ncrm is not None
    ncrm_link = await create_stage_ncrm(
        StageNcrmCreate(
            ncrm_id=UUID(str(ncrm.id)), stage_id=UUID(str(stage.id)), role=NcrmRole.SOLVENT
        ),
        env=env,
    )
    assert ncrm_link is not None

    risk = await create_stage_risk(
        StageRiskCreate(
            stage_id=UUID(str(stage.id)),
            risk_type="process",
            name="Exotherm",
            current_level=8,
            mitigated_level=6,
        ),
        env=env,
    )
    assert risk is not None

    return _Seed(stage, str(component.id), str(ncrm_link.id), str(risk.id))


def _dispatcher_at_stage(env: Environment, seed: _Seed) -> CommandDispatcher:
    """Build a dispatcher whose context stack is parked on the seeded stage."""
    ctx = ContextManager()
    process = seed.stage.process_id
    ctx.push(ContextFrame(track="project", project_id="p", project_name="Proj"))
    ctx.push(
        ContextFrame(
            track="stage_focus",
            project_name="Proj",
            process_id=str(process),
            route_label="1.1",
            stage_id=str(seed.stage.id),
            stage_name="Reaction",
        )
    )
    return CommandDispatcher(ctx, SessionState(), _StubScreen(), env)  # type: ignore[arg-type]


@pytest.mark.integration
async def test_selecting_component_opens_focus_and_back_returns_to_stage(
    temp_env: Environment,
) -> None:
    """A component row pushes component_focus; popping lands back on the stage."""
    seed = await _seed(temp_env)
    dispatcher = _dispatcher_at_stage(temp_env, seed)

    await dispatcher.activate_list_selection(
        ListItem(label="Caffeine", item_id=f"component:{seed.component_id}")
    )

    assert dispatcher.ctx.current.track == "component_focus"
    # The component frame was pushed onto the stage frame, not the route.
    dispatcher.ctx.pop()
    assert dispatcher.ctx.current.track == "stage_focus"


@pytest.mark.integration
async def test_selecting_risk_opens_edit_form_and_persists(temp_env: Environment) -> None:
    """A risk row opens an edit form whose completion updates the risk."""
    seed = await _seed(temp_env)
    dispatcher = _dispatcher_at_stage(temp_env, seed)

    await dispatcher.activate_list_selection(
        ListItem(label="Exotherm", item_id=f"risk:{seed.risk_id}")
    )
    assert dispatcher.prompt_state is not None

    # Fields: risk_type, name, description, current_level, proposed_mitigation,
    # mitigated_level. Empty input keeps the prefilled default.
    await dispatcher.advance_prompt("")  # risk_type
    await dispatcher.advance_prompt("Runaway exotherm")  # name
    await dispatcher.advance_prompt("")  # description
    await dispatcher.advance_prompt("4")  # current_level
    await dispatcher.advance_prompt("")  # proposed_mitigation
    await dispatcher.advance_prompt("1")  # mitigated_level

    assert dispatcher.prompt_state is None
    assert dispatcher.take_notice() == ("Updated risk 'Runaway exotherm'.", "success")
    risks = await list_risks_for_stage(UUID(str(seed.stage.id)), temp_env)
    assert len(risks) == 1
    assert risks[0].name == "Runaway exotherm"
    assert (risks[0].current_level, risks[0].mitigated_level) == (4, 1)


@pytest.mark.integration
async def test_selecting_ncrm_opens_role_form_and_persists(temp_env: Environment) -> None:
    """An NCRM row opens a role-select form whose completion updates the link."""
    seed = await _seed(temp_env)
    dispatcher = _dispatcher_at_stage(temp_env, seed)

    await dispatcher.activate_list_selection(
        ListItem(label="methanol", item_id=f"ncrm:{seed.ncrm_link_id}")
    )
    assert dispatcher.prompt_state is not None
    assert dispatcher.prompt_state.is_select_field

    await dispatcher.advance_prompt(NcrmRole.CATALYST.value)

    assert dispatcher.prompt_state is None
    assert dispatcher.take_notice() == ("NCRM role updated.", "success")
    links = await list_ncrms_for_stage(UUID(str(seed.stage.id)), temp_env)
    assert len(links) == 1
    assert links[0].role is NcrmRole.CATALYST
