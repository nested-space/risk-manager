"""Shared risk add/edit/render flows for the focus and risk-mode screens.

The route, stage, component, and risk-mode screens all create, edit, and render
risks against their focused entity. These flows live here as functions taking the
owning dispatcher (``app``) so every screen shares one implementation: the route
and focus screens add risks to their entity, while risk-mode aggregates and edits
risks across the active scope.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..model.tables import Component, ManufacturingProcess, Project, Stage
from ..operations.component_risks_operations import (
    create_component_risk,
    list_risks_for_component,
    update_component_risk,
)
from ..operations.manufacturing_process_operations import list_processes_for_project
from ..operations.manufacturing_process_risk_operations import (
    create_manufacturing_process_risk,
    list_risks_for_process,
    update_manufacturing_process_risk,
)
from ..operations.stage_risk_operations import (
    create_stage_risk,
    list_risks_for_stage,
    update_stage_risk,
)
from ..repl_engine.list_navigator import ListItem
from ..schema.create import ComponentRiskCreate, ManufacturingProcessRiskCreate, StageRiskCreate
from ..schema.update import ComponentRiskUpdate, ManufacturingProcessRiskUpdate, StageRiskUpdate
from . import lookup, risk_forms
from .form_fields import optional_int
from .renderers.risk_renderer import render_risk_table

if TYPE_CHECKING:
    from .commands import CommandDispatcher


def _row(risk: Any, scope: str) -> dict[str, Any]:
    """Build a risk-table row dict for *risk* under the given *scope* label."""
    return {
        "risk_type": risk.risk_type,
        "name": risk.name,
        "current_level": risk.current_level,
        "mitigated_level": risk.mitigated_level,
        "scope": scope,
    }


# --- rendering -------------------------------------------------------------


async def render_risk_mode(  # pylint: disable=too-many-return-statements  # one return per risk scope
    app: CommandDispatcher,
) -> list[str]:
    """Render the risk table for the active risk scope."""
    scope = app.ctx.current.risk_scope or "project"
    if scope == "project":
        project = await lookup.current_project(app.ctx, app.env)
        if project is None:
            return ["Project not found."]
        return await render_project_risks(app, project)
    if scope == "process":
        process = await lookup.current_process(app.ctx, app.env)
        if process is None:
            return ["Route not found."]
        return await render_process_risks(app, process)
    if scope == "stage":
        stage = await lookup.current_stage(app.ctx, app.env)
        if stage is None:
            return ["Stage not found."]
        return await render_stage_risks(app, stage)
    component = await lookup.current_component(app.ctx, app.env)
    if component is None:
        return ["Component not found."]
    return await render_component_risks(app, component)


async def render_project_risks(app: CommandDispatcher, project: Project) -> list[str]:
    """Render every risk across the project's routes."""
    processes = await list_processes_for_project(UUID(str(project.id)), app.env)
    risks: list[dict[str, Any]] = []
    for process in processes:
        label = f"{process.route_number}.{process.process_number}"
        for risk in await list_risks_for_process(UUID(str(process.id)), app.env):
            risks.append(_row(risk, label))
    return await render_risk_table(
        risks, scope_label=f"project · {project.name}", width=app.screen.width
    )


async def render_process_risks(app: CommandDispatcher, process: ManufacturingProcess) -> list[str]:
    """Render the route's risks."""
    label = app.ctx.current.route_label or "process"
    risks = [
        _row(risk, label) for risk in await list_risks_for_process(UUID(str(process.id)), app.env)
    ]
    return await render_risk_table(
        risks, scope_label=f"route {app.ctx.current.route_label or ''}", width=app.screen.width
    )


async def render_stage_risks(app: CommandDispatcher, stage: Stage) -> list[str]:
    """Render the stage's risks."""
    risks = [
        _row(risk, stage.name) for risk in await list_risks_for_stage(UUID(str(stage.id)), app.env)
    ]
    return await render_risk_table(
        risks, scope_label=f"stage · {stage.name}", width=app.screen.width
    )


async def render_component_risks(app: CommandDispatcher, component: Component) -> list[str]:
    """Render the component's risks."""
    name = app.ctx.current.component_name or "component"
    risks = [
        _row(risk, name)
        for risk in await list_risks_for_component(UUID(str(component.id)), app.env)
    ]
    return await render_risk_table(risks, scope_label=f"component · {name}", width=app.screen.width)


# --- creating --------------------------------------------------------------


async def create_stage_risk_from_prompt(
    app: CommandDispatcher, stage: Stage, payload: dict[str, str | None]
) -> list[str]:
    """Create a stage risk from completed-prompt *payload*."""
    risk = await create_stage_risk(
        StageRiskCreate(
            stage_id=UUID(str(stage.id)),
            risk_type=payload.get("risk_type") or "risk",
            name=payload.get("name") or "Unnamed risk",
            description=payload.get("description"),
            current_level=optional_int(payload.get("current_level")),
            proposed_mitigation=payload.get("proposed_mitigation"),
            mitigated_level=optional_int(payload.get("mitigated_level")),
        ),
        app.env,
    )
    if risk is None:
        return await app.refresh_with_notice("Failed to create stage risk.", "error")
    return await app.refresh_with_notice("Stage risk created.")


async def create_process_risk_from_prompt(
    app: CommandDispatcher, process: ManufacturingProcess, payload: dict[str, str | None]
) -> list[str]:
    """Create a process (route) risk from completed-prompt *payload*."""
    risk = await create_manufacturing_process_risk(
        ManufacturingProcessRiskCreate(
            manufacturing_process_id=UUID(str(process.id)),
            risk_type=payload.get("risk_type") or "risk",
            name=payload.get("name") or "Unnamed risk",
            description=payload.get("description"),
            current_level=optional_int(payload.get("current_level")),
            proposed_mitigation=payload.get("proposed_mitigation"),
            mitigated_level=optional_int(payload.get("mitigated_level")),
        ),
        app.env,
    )
    if risk is None:
        return await app.refresh_with_notice("Failed to create process risk.", "error")
    return await app.refresh_with_notice("Process risk created.")


async def create_component_risk_from_prompt(
    app: CommandDispatcher, component: Component, payload: dict[str, str | None]
) -> list[str]:
    """Create a component risk from completed-prompt *payload*."""
    risk = await create_component_risk(
        ComponentRiskCreate(
            component_id=UUID(str(component.id)),
            risk_type=payload.get("risk_type") or "risk",
            name=payload.get("name") or "Unnamed risk",
            description=payload.get("description"),
            current_level=optional_int(payload.get("current_level")),
            proposed_mitigation=payload.get("proposed_mitigation"),
            mitigated_level=optional_int(payload.get("mitigated_level")),
        ),
        app.env,
    )
    if risk is None:
        return await app.refresh_with_notice("Failed to create component risk.", "error")
    return await app.refresh_with_notice("Component risk created.")


# --- editing ---------------------------------------------------------------


async def start_stage_risk_edit_form(app: CommandDispatcher, risk_id: str) -> list[str]:
    """Open an edit form for the stage risk with id *risk_id*."""
    stage = await lookup.current_stage(app.ctx, app.env)
    if stage is None:
        return ["Stage not found."]
    risk = next(
        (
            candidate
            for candidate in await list_risks_for_stage(UUID(str(stage.id)), app.env)
            if str(candidate.id) == risk_id
        ),
        None,
    )
    if risk is None:
        return ["Risk not found."]
    return app.modal.start_prompt(
        risk_forms.risk_edit_fields(risk),
        lambda **payload: update_stage_risk_from_prompt(app, risk_id, payload),
        title="Edit risk",
    )


async def start_process_risk_edit_form(app: CommandDispatcher, risk_id: str) -> list[str]:
    """Open an edit form for the process risk with id *risk_id*."""
    process = await lookup.current_process(app.ctx, app.env)
    if process is None:
        return ["Route not found."]
    risk = next(
        (
            candidate
            for candidate in await list_risks_for_process(UUID(str(process.id)), app.env)
            if str(candidate.id) == risk_id
        ),
        None,
    )
    if risk is None:
        return ["Risk not found."]
    return app.modal.start_prompt(
        risk_forms.risk_edit_fields(risk),
        lambda **payload: update_process_risk_from_prompt(app, risk_id, payload),
        title="Edit risk",
    )


async def start_component_risk_edit_form(app: CommandDispatcher, risk_id: str) -> list[str]:
    """Open an edit form for the component risk with id *risk_id*."""
    component = await lookup.current_component(app.ctx, app.env)
    if component is None:
        return ["Component not found."]
    risk = next(
        (
            candidate
            for candidate in await list_risks_for_component(UUID(str(component.id)), app.env)
            if str(candidate.id) == risk_id
        ),
        None,
    )
    if risk is None:
        return ["Risk not found."]
    return app.modal.start_prompt(
        risk_forms.risk_edit_fields(risk),
        lambda **payload: update_component_risk_from_prompt(app, risk_id, payload),
        title="Edit risk",
    )


async def update_stage_risk_from_prompt(
    app: CommandDispatcher, risk_id: str, payload: dict[str, str | None]
) -> list[str]:
    """Apply the edit-form *payload* to the stage risk with id *risk_id*."""
    updated = await update_stage_risk(
        UUID(risk_id),
        StageRiskUpdate(
            risk_type=payload.get("risk_type") or None,
            name=payload.get("name") or None,
            description=payload.get("description"),
            current_level=optional_int(payload.get("current_level")),
            proposed_mitigation=payload.get("proposed_mitigation"),
            mitigated_level=optional_int(payload.get("mitigated_level")),
        ),
        app.env,
    )
    if updated is None:
        return await app.refresh_with_notice("Failed to update risk.", "error")
    return await app.refresh_with_notice(f"Updated risk '{updated.name}'.")


async def update_process_risk_from_prompt(
    app: CommandDispatcher, risk_id: str, payload: dict[str, str | None]
) -> list[str]:
    """Apply the edit-form *payload* to the process risk with id *risk_id*."""
    updated = await update_manufacturing_process_risk(
        UUID(risk_id),
        ManufacturingProcessRiskUpdate(
            risk_type=payload.get("risk_type") or None,
            name=payload.get("name") or None,
            description=payload.get("description"),
            current_level=optional_int(payload.get("current_level")),
            proposed_mitigation=payload.get("proposed_mitigation"),
            mitigated_level=optional_int(payload.get("mitigated_level")),
        ),
        app.env,
    )
    if updated is None:
        return await app.refresh_with_notice("Failed to update risk.", "error")
    return await app.refresh_with_notice(f"Updated risk '{updated.name}'.")


async def update_component_risk_from_prompt(
    app: CommandDispatcher, risk_id: str, payload: dict[str, str | None]
) -> list[str]:
    """Apply the edit-form *payload* to the component risk with id *risk_id*."""
    updated = await update_component_risk(
        UUID(risk_id),
        ComponentRiskUpdate(
            risk_type=payload.get("risk_type") or None,
            name=payload.get("name") or None,
            description=payload.get("description"),
            current_level=optional_int(payload.get("current_level")),
            proposed_mitigation=payload.get("proposed_mitigation"),
            mitigated_level=optional_int(payload.get("mitigated_level")),
        ),
        app.env,
    )
    if updated is None:
        return await app.refresh_with_notice("Failed to update risk.", "error")
    return await app.refresh_with_notice(f"Updated risk '{updated.name}'.")


def start_risk_edit_picker(
    app: CommandDispatcher,
    risks: Sequence[Any],
    open_edit: Callable[[str], Any],
) -> list[str]:
    """Show a picker over *risks* that opens *open_edit* for the chosen id."""
    if not risks:
        return ["No risks yet."]
    items = [
        ListItem(label=f"{risk.risk_type} · {risk.name}", item_id=str(risk.id)) for risk in risks
    ]
    return app.modal.start_picker("Edit risk", items, lambda item: open_edit(item.item_id))
