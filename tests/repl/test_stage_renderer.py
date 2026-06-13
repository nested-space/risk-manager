"""Integration tests for the Stage Focus sectioned-page renderer.

Exercises ``gather_stage_sections`` + ``render_stage_screen`` end-to-end against a
real (in-memory) SQLite database, seeding components, NCRMs, and risks so the
section rules and box tables are rendered from genuine operation results.
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
from riskmanager_cli.operations.stage_ncrm_operations import create_stage_ncrm
from riskmanager_cli.operations.stage_operations import create_stage
from riskmanager_cli.operations.stage_risk_operations import create_stage_risk
from riskmanager_cli.repl.renderers.stage_renderer import (
    gather_stage_sections,
    render_stage_screen,
    stage_targets,
)
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


async def _new_component(env: Environment, process_id: str, name: str) -> str:
    material = await create_material(MaterialCreate(name=name), env=env)
    assert material is not None
    component = await create_component(
        ComponentCreate(process_id=UUID(process_id), material_id=UUID(str(material.id))),
        env=env,
    )
    assert component is not None
    return str(component.id)


async def _seed_links(env: Environment, process_id: str, stage_id: str) -> None:
    """Link two reactants, one product, and one NCRM to *stage_id*."""
    components = {
        name: await _new_component(env, process_id, name) for name in ("A", "B", "C")
    }
    for name, role in [
        ("C", "product"),  # added first to prove reactants sort ahead
        ("A", "reactant"),
        ("B", "reactant"),
    ]:
        link = await create_stage_component(
            StageComponentCreate(
                stage_id=UUID(stage_id),
                component_id=UUID(components[name]),
                component_type=role,
            ),
            env=env,
        )
        assert link is not None

    ncrm = await create_ncrm_library_entry(
        NcrmLibraryCreate(display_name="methanol", name="methanol"), env=env
    )
    assert ncrm is not None
    ncrm_link = await create_stage_ncrm(
        StageNcrmCreate(
            ncrm_id=UUID(str(ncrm.id)), stage_id=UUID(stage_id), role=NcrmRole.SOLVENT
        ),
        env=env,
    )
    assert ncrm_link is not None


async def _seed_stage(env: Environment, *, with_risk: bool, with_links: bool = True) -> Stage:
    """Seed a project → process → stage and return the stage.

    When *with_links* is true the stage gets two reactants, one product, and one
    NCRM link; when *with_risk* is true it also gets a single risk.
    """
    seed = await create_material(MaterialCreate(name="Seed"), env=env)
    assert seed is not None
    project = await create_project(
        ProjectCreate(name="StageProj", therapy_area=TA.ONCOLOGY, material_id=UUID(str(seed.id))),
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

    if with_links:
        await _seed_links(env, str(process.id), str(stage.id))

    if with_risk:
        risk = await create_stage_risk(
            StageRiskCreate(
                stage_id=UUID(str(stage.id)),
                risk_type="process",
                name="Exotherm",
                current_level=4,
                mitigated_level=3,
            ),
            env=env,
        )
        assert risk is not None

    return stage


@pytest.mark.integration
async def test_render_stage_screen_sections_and_tables_are_populated(
    temp_env: Environment,
) -> None:
    """The page renders a stage title, section rules, and populated tables."""
    stage = await _seed_stage(temp_env, with_risk=True)

    sections = await gather_stage_sections(stage, temp_env)
    lines = render_stage_screen(stage, sections, width=120)
    joined = "\n".join(lines)

    # Stage title and its underline open the page at column zero.
    assert lines[0] == "Stage 1"
    assert lines[1] == "─" * len("Stage 1")

    # Each section has a titled rule.
    assert any("─ Components " in line for line in lines)
    assert any("─ NCRMs " in line for line in lines)
    assert any("─ Risks " in line for line in lines)

    # Box tables with their column headers are present.
    assert any(line.lstrip().startswith("┌") for line in lines)
    for header in ("Name", "Role", "Description", "Level", "Mitigation", "Mitigated level"):
        assert header in joined

    # Component/NCRM rows are rendered with title-cased roles.
    for name, role in [("A", "Reactant"), ("B", "Reactant"), ("C", "Product")]:
        assert name in joined and role in joined
    assert "methanol" in joined and "Solvent" in joined
    # The risk row shows its name and severity-labelled levels (current 4, mitigated 3).
    assert "Exotherm" in joined and "High (4)" in joined and "Medium (3)" in joined

    # Reactants sort ahead of the product despite the product being linked first.
    a_row = next(i for i, line in enumerate(lines) if "│ A " in line)
    c_row = next(i for i, line in enumerate(lines) if "│ C " in line)
    assert a_row < c_row


@pytest.mark.integration
async def test_render_stage_screen_caret_marks_only_the_selected_row(
    temp_env: Environment,
) -> None:
    """Passing ``selected_id`` puts ``> `` on exactly that row and nowhere else."""
    stage = await _seed_stage(temp_env, with_risk=True)
    sections = await gather_stage_sections(stage, temp_env)
    targets = stage_targets(sections)
    # Select the second target so the caret is clearly not just the first row.
    chosen = targets[1]

    lines = render_stage_screen(stage, sections, width=120, selected_id=chosen.item_id)

    caret_lines = [line for line in lines if line.startswith("> ")]
    assert len(caret_lines) == 1
    assert chosen.label in caret_lines[0]


@pytest.mark.integration
async def test_render_stage_screen_empty_sections_show_placeholders(
    temp_env: Environment,
) -> None:
    """A stage with no links/risks shows the empty-state placeholders."""
    stage = await _seed_stage(temp_env, with_risk=False, with_links=False)

    sections = await gather_stage_sections(stage, temp_env)
    assert stage_targets(sections) == []
    lines = render_stage_screen(stage, sections, width=80)
    joined = "\n".join(lines)

    assert "(none)" in joined  # components + NCRMs empty
    assert "(no risks recorded)" in joined
    # No caret appears when there is nothing selectable.
    assert not any(line.startswith("> ") for line in lines)
