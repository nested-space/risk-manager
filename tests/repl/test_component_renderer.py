"""Integration tests for the Component Focus sectioned-page renderer.

Exercises ``gather_component_sections`` + ``render_component_screen`` end-to-end
against a real (in-memory) SQLite database, seeding a component with salts and
risks so the section rules and box tables are rendered from genuine operation
results.
"""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.model.tables import Component, Material
from riskmanager_cli.operations.component_operations import (
    component_display_name,
    create_component,
)
from riskmanager_cli.operations.component_risks_operations import create_component_risk
from riskmanager_cli.operations.component_salt_operations import create_component_salt
from riskmanager_cli.operations.counterion_operations import create_counterion
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.repl.renderers.component_renderer import (
    component_targets,
    gather_component_sections,
    render_component_screen,
)
from riskmanager_cli.repl_engine.viewport import parse
from riskmanager_cli.schema.create import (
    ComponentCreate,
    ComponentRiskCreate,
    ComponentSaltCreate,
    CounterionCreate,
    ManufacturingProcessCreate,
    MaterialCreate,
    ProjectCreate,
)


async def _seed_component(
    env: Environment, *, with_salt: bool, with_risk: bool
) -> tuple[Component, Material]:
    """Seed a project → process → component and return the component + material.

    When *with_salt* is true the component gets one fully-defined salt; when
    *with_risk* is true it gets a single risk.
    """
    material = await create_material(MaterialCreate(name="Widget", smiles="CCO"), env=env)
    assert material is not None
    project = await create_project(
        ProjectCreate(
            name="CompProj", therapy_area=TA.ONCOLOGY, material_id=UUID(str(material.id))
        ),
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
        ComponentCreate(
            process_id=UUID(str(process.id)),
            material_id=UUID(str(material.id)),
            control_strategy_role="API",
            is_isolated=True,
        ),
        env=env,
    )
    assert component is not None

    if with_salt:
        counterion = await create_counterion(CounterionCreate(name="Chloride"), env=env)
        assert counterion is not None
        salt = await create_component_salt(
            ComponentSaltCreate(
                component_id=UUID(str(component.id)),
                counterion_id=UUID(str(counterion.id)),
                stoichiometry=1.0,
                is_fully_defined=True,
            ),
            env=env,
        )
        assert salt is not None

    if with_risk:
        risk = await create_component_risk(
            ComponentRiskCreate(
                component_id=UUID(str(component.id)),
                risk_type="purity",
                name="Residual solvent",
                current_level=4,
                mitigated_level=2,
            ),
            env=env,
        )
        assert risk is not None

    return component, material


@pytest.mark.integration
async def test_render_component_screen_sections_and_tables_are_populated(
    temp_env: Environment,
) -> None:
    """The page renders a component title, section rules, and populated tables."""
    component, material = await _seed_component(temp_env, with_salt=True, with_risk=True)

    sections = await gather_component_sections(component, material, temp_env)
    display_name = await component_display_name(component, temp_env)
    lines = render_component_screen(sections, display_name=display_name, width=120)
    joined = "\n".join(lines)

    # The title shows the salt-form name (stoichiometry 1 omits the number).
    assert display_name == "Widget·Chloride"
    assert lines[0] == "Component: Widget·Chloride"
    assert lines[1] == "─" * len("Component: Widget·Chloride")

    # Each section has a titled rule.
    assert any("─ Details " in line for line in lines)
    assert any("─ Salts " in line for line in lines)
    assert any("─ Risks " in line for line in lines)

    # Box tables are present.
    assert any(line.lstrip().startswith("┌") for line in lines)

    # Details show material, control role, isolated flag, and SMILES.
    assert "Widget" in joined and "API" in joined and "yes" in joined and "CCO" in joined
    # The salt row shows the counterion and its stoichiometry.
    assert "Chloride" in joined and "1" in joined
    # The risk row shows its name and severity-labelled levels (current 4, mitigated 2).
    assert "Residual solvent" in joined and "H (4)" in joined and "L (2)" in joined


@pytest.mark.integration
async def test_component_targets_select_salt_and_risk_rows(temp_env: Environment) -> None:
    """Salt and risk rows are selectable (salts first); details carry no target."""
    component, material = await _seed_component(temp_env, with_salt=True, with_risk=True)
    sections = await gather_component_sections(component, material, temp_env)

    targets = component_targets(sections)
    assert [str(t.item_id).split(":", 1)[0] for t in targets] == ["salt", "risk"]
    salt_target, risk_target = targets
    assert salt_target.label == "Chloride"

    display_name = await component_display_name(component, temp_env)
    lines = render_component_screen(
        sections,
        display_name=display_name,
        width=120,
        selected_id=salt_target.item_id,
    )
    caret_lines = [line for line in parse(lines).lines if line.startswith("> ")]
    assert len(caret_lines) == 1
    assert salt_target.label in caret_lines[0]


@pytest.mark.integration
async def test_render_component_screen_empty_sections_show_placeholders(
    temp_env: Environment,
) -> None:
    """A component with no salts/risks shows the empty-state placeholders."""
    component, material = await _seed_component(temp_env, with_salt=False, with_risk=False)

    sections = await gather_component_sections(component, material, temp_env)
    assert component_targets(sections) == []
    display_name = await component_display_name(component, temp_env)
    lines = render_component_screen(sections, display_name=display_name, width=80)
    joined = "\n".join(lines)

    assert "(no salts)" in joined
    assert "(no risks recorded)" in joined
    # No caret appears when there is nothing selectable.
    assert not any(line.startswith("> ") for line in parse(lines).lines)
