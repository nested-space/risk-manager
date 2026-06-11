"""Integration tests for REPL entity-creation flows.

These drive the :class:`CommandDispatcher` end-to-end (guided prompts and the
typeahead picker) to verify that ``/add project``, ``/add process`` and
``/add salt`` persist the expected records.
"""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.operations.component_operations import create_component
from riskmanager_cli.operations.component_salt_operations import list_salts_for_component
from riskmanager_cli.operations.counterion_operations import create_counterion
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
    list_processes_for_project,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project, list_projects
from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl.session_state import SessionState
from riskmanager_cli.schema.create import (
    ComponentCreate,
    CounterionCreate,
    ManufacturingProcessCreate,
    MaterialCreate,
    ProjectCreate,
)


class _StubScreen:
    """Minimal screen stand-in exposing only the ``width`` used by rendering."""

    width = 80


def _make_dispatcher(env: Environment) -> CommandDispatcher:
    """Build a dispatcher wired to a fresh context, session and stub screen."""
    return CommandDispatcher(ContextManager(), SessionState(), _StubScreen(), env)  # type: ignore[arg-type]


@pytest.mark.integration
async def test_add_project_creates_project_via_picker(temp_env: Environment) -> None:
    """`/add project` collects name + therapy area then picks a material."""
    await create_material(MaterialCreate(name="Caffeine"), env=temp_env)
    dispatcher = _make_dispatcher(temp_env)

    await dispatcher.dispatch("/add project")
    await dispatcher.advance_prompt("AlphaProject")
    await dispatcher.advance_prompt(TA.ONCOLOGY.value)

    # The material picker is now active; filter to the seeded material and pick.
    assert dispatcher.picker_state is not None
    dispatcher.update_picker_query("caf")
    await dispatcher.picker_select()

    assert dispatcher.take_notice() == ("Created project 'AlphaProject'.", "success")
    projects = await list_projects(env=temp_env)
    assert [project.name for project in projects] == ["AlphaProject"]
    assert projects[0].therapy_area is TA.ONCOLOGY


@pytest.mark.integration
async def test_add_project_with_no_materials_reports_guidance(temp_env: Environment) -> None:
    """`/add project` aborts with guidance when no materials exist to link."""
    dispatcher = _make_dispatcher(temp_env)

    await dispatcher.dispatch("/add project")
    await dispatcher.advance_prompt("AlphaProject")
    result = await dispatcher.advance_prompt(TA.ONCOLOGY.value)

    assert dispatcher.picker_state is None
    assert any("material first" in line for line in result)
    assert await list_projects(env=temp_env) == []


@pytest.mark.integration
async def test_add_process_creates_manufacturing_process(temp_env: Environment) -> None:
    """`/add process` persists a manufacturing process under the open project."""
    material = await create_material(MaterialCreate(name="Caffeine"), env=temp_env)
    assert material is not None
    project = await create_project(
        ProjectCreate(
            name="AlphaProject",
            therapy_area=TA.ONCOLOGY,
            material_id=UUID(str(material.id)),
        ),
        env=temp_env,
    )
    assert project is not None

    dispatcher = _make_dispatcher(temp_env)
    dispatcher.ctx.push(
        ContextFrame(track="project", project_id=str(project.id), project_name=project.name)
    )

    await dispatcher.dispatch("/add process")
    await dispatcher.advance_prompt("1")
    await dispatcher.advance_prompt("1")

    assert dispatcher.take_notice() == ("Created process 1.1.", "success")
    processes = await list_processes_for_project(UUID(str(project.id)), env=temp_env)
    assert len(processes) == 1
    assert (processes[0].route_number, processes[0].process_number) == (1, 1)


@pytest.mark.integration
async def test_add_process_rejects_zero_numbers(temp_env: Environment) -> None:
    """`/add process` rejects route/process numbers below 1 without persisting."""
    material = await create_material(MaterialCreate(name="Caffeine"), env=temp_env)
    assert material is not None
    project = await create_project(
        ProjectCreate(
            name="AlphaProject",
            therapy_area=TA.ONCOLOGY,
            material_id=UUID(str(material.id)),
        ),
        env=temp_env,
    )
    assert project is not None

    dispatcher = _make_dispatcher(temp_env)
    dispatcher.ctx.push(
        ContextFrame(track="project", project_id=str(project.id), project_name=project.name)
    )

    await dispatcher.dispatch("/add process")
    await dispatcher.advance_prompt("0")
    result = await dispatcher.advance_prompt("1")

    assert any("1 or greater" in line for line in result)
    assert await list_processes_for_project(UUID(str(project.id)), env=temp_env) == []


@pytest.mark.integration
async def test_add_salt_links_counterion_to_component(temp_env: Environment) -> None:
    """`/add salt` picks a counterion then records the salt on the component."""
    material = await create_material(MaterialCreate(name="Caffeine"), env=temp_env)
    assert material is not None
    project = await create_project(
        ProjectCreate(
            name="AlphaProject",
            therapy_area=TA.ONCOLOGY,
            material_id=UUID(str(material.id)),
        ),
        env=temp_env,
    )
    assert project is not None
    process = await create_manufacturing_process(
        ManufacturingProcessCreate(
            project_id=UUID(str(project.id)), route_number=1, process_number=1
        ),
        env=temp_env,
    )
    assert process is not None
    component = await create_component(
        ComponentCreate(
            process_id=UUID(str(process.id)),
            material_id=UUID(str(material.id)),
            is_isolated=False,
        ),
        env=temp_env,
    )
    assert component is not None
    await create_counterion(CounterionCreate(name="Chloride"), env=temp_env)

    dispatcher = _make_dispatcher(temp_env)
    dispatcher.ctx.push(
        ContextFrame(
            track="component_focus",
            project_id=str(project.id),
            process_id=str(process.id),
            component_id=str(component.id),
            component_name="Caffeine",
        )
    )

    await dispatcher.dispatch("/add salt")
    assert dispatcher.picker_state is not None
    dispatcher.update_picker_query("chlor")
    await dispatcher.picker_select()

    # The picker hands off to a stoichiometry / is-fully-defined prompt.
    assert dispatcher.prompt_state is not None
    await dispatcher.advance_prompt("1.0")
    await dispatcher.advance_prompt("true")

    assert dispatcher.take_notice() == ("Created salt record.", "success")
    salts = await list_salts_for_component(UUID(str(component.id)), env=temp_env)
    assert len(salts) == 1
    assert salts[0].counterion_id is not None
