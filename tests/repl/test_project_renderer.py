"""Integration tests for the Project sectioned-page renderer.

Exercises ``render_project_screen`` end-to-end against a real (in-memory) SQLite
database, seeding a project with routes and process risks so the section rules
and box tables are rendered from genuine operation results.
"""

from uuid import UUID

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.model.enums import TA
from riskmanager_cli.model.tables import Project
from riskmanager_cli.operations.manufacturing_process_operations import (
    create_manufacturing_process,
)
from riskmanager_cli.operations.manufacturing_process_risk_operations import (
    create_manufacturing_process_risk,
)
from riskmanager_cli.operations.material_operations import create_material
from riskmanager_cli.operations.project_operations import create_project
from riskmanager_cli.repl.renderers.project_renderer import render_project_screen
from riskmanager_cli.schema.create import (
    ManufacturingProcessCreate,
    ManufacturingProcessRiskCreate,
    MaterialCreate,
    ProjectCreate,
)


async def _seed_project(env: Environment, *, with_risk: bool) -> Project:
    """Seed a project with one route and (optionally) a high-severity risk."""
    material = await create_material(MaterialCreate(name="Benzene", smiles="C1=CC=CC=C1"), env=env)
    assert material is not None
    project = await create_project(
        ProjectCreate(name="Test", therapy_area=TA.ONCOLOGY, material_id=UUID(str(material.id))),
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

    if with_risk:
        risk = await create_manufacturing_process_risk(
            ManufacturingProcessRiskCreate(
                manufacturing_process_id=UUID(str(process.id)),
                risk_type="Safety",
                name="Exotherm",
                current_level=4,  # High on the 1-5 scale
            ),
            env=env,
        )
        assert risk is not None

    return project


@pytest.mark.integration
async def test_render_project_screen_sections_and_tables_are_populated(
    temp_env: Environment,
) -> None:
    """The page renders three titled sections with populated box tables."""
    project = await _seed_project(temp_env, with_risk=True)

    route_lines = ["Recent", "▶ Route 1 Process 1"]
    lines = await render_project_screen(project, temp_env, route_lines=route_lines)
    joined = "\n".join(lines)

    # Each section has a titled rule.
    assert any("─ Project Details " in line for line in lines)
    assert any("─ Routes " in line for line in lines)
    assert any("─ Risks " in line for line in lines)

    # Box tables with their column headers are present.
    assert any(line.lstrip().startswith("┌") for line in lines)
    for header in ("Property", "Value", "Level", "Number"):
        assert header in joined

    # Project Details rows show the project's name, therapy area, and SMILES.
    # The seeded SMILES is canonicalized on create (benzene -> "c1ccccc1").
    assert "Test" in joined
    assert TA.ONCOLOGY.value in joined
    assert "SMILES" in joined
    assert "c1ccccc1" in joined

    # The Risks table tallies the seeded level-4 risk into the High band, and the
    # 1-5 scale adds a Very Low row.
    risks_index = next(i for i, line in enumerate(lines) if "─ Risks " in line)
    # Match the "High" band specifically, not the "Very High" row above it.
    high_row = next(line for line in lines[risks_index:] if "│ High" in line)
    assert "1" in high_row
    assert any("Very Low" in line and "│" in line for line in lines[risks_index:])


@pytest.mark.integration
async def test_render_project_screen_places_routes_under_the_routes_rule(
    temp_env: Environment,
) -> None:
    """Pre-rendered route lines appear (indented) beneath the Routes rule."""
    project = await _seed_project(temp_env, with_risk=False)

    lines = await render_project_screen(project, temp_env, route_lines=["▶ Route 1 Process 1"])

    routes_index = next(i for i, line in enumerate(lines) if "─ Routes " in line)
    route_line = next(line for line in lines[routes_index:] if "Route 1 Process 1" in line)
    assert route_line.startswith("  ")  # indented into the body gutter
    # With no risks every severity counts as zero.
    risks_index = next(i for i, line in enumerate(lines) if "─ Risks " in line)
    assert all("0" in line for line in lines[risks_index:] if line.strip().startswith("│ Low"))


@pytest.mark.integration
async def test_render_project_screen_without_route_lines_shows_a_count(
    temp_env: Environment,
) -> None:
    """A non-interactive render (no ``route_lines``) shows a plain route count."""
    project = await _seed_project(temp_env, with_risk=False)

    lines = await render_project_screen(project, temp_env)
    joined = "\n".join(lines)

    assert "1 total" in joined
