"""Shared stage/component/NCRM mutation flows.

The route screen orchestrates editing, deleting, assigning, and linking stages
and components; the stage- and component-focus screens edit/delete the same
entities directly. These flows live here as functions taking the owning
dispatcher (``app``) so all three screens share one implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from ..model.enums import NcrmRole
from ..model.tables import Component, ManufacturingProcess, Stage
from ..operations.component_operations import (
    delete_component,
    get_component_by_id,
    update_component,
)
from ..operations.ncrm_library_operations import (
    get_ncrm_by_display_name,
    list_ncrm_library,
)
from ..operations.stage_component_operations import create_stage_component
from ..operations.stage_ncrm_operations import (
    create_stage_ncrm,
    list_ncrms_for_stage,
    update_stage_ncrm,
)
from ..operations.stage_operations import delete_stage, update_stage
from ..repl_engine.forms import FieldSpec
from ..repl_engine.list_navigator import ListItem
from ..schema.create import StageComponentCreate, StageNcrmCreate
from ..schema.update import ComponentUpdate, StageNcrmUpdate, StageUpdate
from . import lookup, picker_items
from .form_fields import BOOL_OPTIONS, COMPONENT_TYPE_OPTIONS, as_bool, enum_options, optional_int

if TYPE_CHECKING:
    from .commands import CommandDispatcher


# --- stage edit / delete ---------------------------------------------------


def start_stage_edit_form(app: CommandDispatcher, stage: Stage) -> list[str]:
    """Open the edit form for *stage*."""
    return app.modal.start_prompt(
        [
            FieldSpec("name", default=stage.name),
            FieldSpec("number", field_type="int", default=str(stage.number)),
        ],
        lambda **payload: update_stage_from_prompt(app, stage, payload),
        title="Edit stage",
    )


async def update_stage_from_prompt(
    app: CommandDispatcher, stage: Stage, payload: dict[str, str | None]
) -> list[str]:
    """Apply the edit-form *payload* to *stage*."""
    updated = await update_stage(
        UUID(str(stage.id)),
        StageUpdate(name=payload.get("name") or None, number=optional_int(payload.get("number"))),
        app.env,
    )
    if updated is None:
        return await app.refresh_with_notice("Failed to update stage.", "error")
    app.ctx.current.stage_name = updated.name
    app.session.update_context(stage_id=str(updated.id))
    return await app.refresh_with_notice(f"Updated stage '{updated.name}'.")


async def delete_stage_with_confirmation(
    app: CommandDispatcher, stage: Stage, args: list[str]
) -> list[str]:
    """Delete *stage* when ``--confirm`` is present, then leave a focused frame."""
    if "--confirm" not in args:
        return ["Re-run with --confirm to delete the stage."]
    success = await delete_stage(UUID(str(stage.id)), app.env)
    if not success:
        return await app.refresh_with_notice("Stage delete failed.", "error")
    app.pop_focus_to_parent()
    return await app.refresh_with_notice("Stage deleted.")


# --- component edit / delete ----------------------------------------------


def start_component_edit_form(app: CommandDispatcher, component: Component) -> list[str]:
    """Open the edit form for *component*."""
    return app.modal.start_prompt(
        [
            FieldSpec(
                "control_strategy_role", required=False, default=component.control_strategy_role
            ),
            FieldSpec(
                "is_isolated",
                field_type="select",
                options=BOOL_OPTIONS,
                default="true" if component.is_isolated else "false",
            ),
        ],
        lambda **payload: update_component_from_prompt(app, component, payload),
        title="Edit component",
    )


async def update_component_from_prompt(
    app: CommandDispatcher, component: Component, payload: dict[str, str | None]
) -> list[str]:
    """Apply the edit-form *payload* to *component*."""
    updated = await update_component(
        UUID(str(component.id)),
        ComponentUpdate(
            control_strategy_role=payload.get("control_strategy_role"),
            is_isolated=as_bool(payload.get("is_isolated")),
        ),
        app.env,
    )
    if updated is None:
        return await app.refresh_with_notice("Failed to update component.", "error")
    return await app.refresh_with_notice("Component updated.")


async def delete_component_with_confirmation(
    app: CommandDispatcher, component: Component, args: list[str]
) -> list[str]:
    """Delete *component* when ``--confirm`` is present, then leave a focused frame."""
    if "--confirm" not in args:
        return ["Re-run with --confirm to delete the component."]
    success = await delete_component(UUID(str(component.id)), app.env)
    if not success:
        return await app.refresh_with_notice("Component delete failed.", "error")
    app.pop_focus_to_parent()
    return await app.refresh_with_notice("Component deleted.")


# --- stage-NCRM role edit --------------------------------------------------


async def start_stage_ncrm_edit_form(app: CommandDispatcher, link_id: str) -> list[str]:
    """Open a role-edit form for the stage-NCRM link with id *link_id*."""
    stage = await lookup.current_stage(app.ctx, app.env)
    if stage is None:
        return ["Stage not found."]
    link = next(
        (
            candidate
            for candidate in await list_ncrms_for_stage(UUID(str(stage.id)), app.env)
            if str(candidate.id) == link_id
        ),
        None,
    )
    if link is None:
        return ["NCRM link not found."]
    return app.modal.start_prompt(
        [
            FieldSpec(
                "role",
                field_type="select",
                options=enum_options(NcrmRole),
                default=link.role.value,
            )
        ],
        lambda **payload: update_stage_ncrm_from_prompt(app, link_id, payload),
    )


async def update_stage_ncrm_from_prompt(
    app: CommandDispatcher, link_id: str, payload: dict[str, str | None]
) -> list[str]:
    """Apply the role-edit *payload* to the stage-NCRM link with id *link_id*."""
    updated = await update_stage_ncrm(
        UUID(link_id),
        StageNcrmUpdate(role=NcrmRole(payload.get("role") or NcrmRole.REAGENT.value)),
        app.env,
    )
    if updated is None:
        return await app.refresh_with_notice("Failed to update NCRM role.", "error")
    return await app.refresh_with_notice("NCRM role updated.")


# --- assign an existing component to a stage -------------------------------


async def start_stage_component_picker(
    app: CommandDispatcher, stage: Stage, process: ManufacturingProcess
) -> list[str]:
    """Open a picker of the process's components to assign one to *stage*."""
    items = await picker_items.process_component_items(app.env, process)
    if not items:
        return [
            "No components yet. Create one at the route level with /add component <material>.",
        ]
    return app.modal.start_picker(
        "Assign component to stage",
        items,
        lambda item: start_assign_role_prompt(app, stage, item),
    )


def start_assign_role_prompt(
    app: CommandDispatcher, stage: Stage, component_item: ListItem
) -> list[str]:
    """Prompt for the component-type role, then assign the component to *stage*."""
    return app.modal.start_prompt(
        [FieldSpec("component_type", field_type="select", options=COMPONENT_TYPE_OPTIONS)],
        lambda **payload: assign_component_to_stage(app, stage, component_item.item_id, payload),
    )


async def assign_component_to_stage(
    app: CommandDispatcher, stage: Stage, component_id: str, payload: dict[str, str | None]
) -> list[str]:
    """Create the stage-component link from a completed role prompt."""
    link = await create_stage_component(
        StageComponentCreate(
            stage_id=UUID(str(stage.id)),
            component_id=UUID(component_id),
            component_type=payload.get("component_type") or "reactant",
        ),
        app.env,
    )
    if link is None:
        return await app.refresh_with_notice("Failed to assign component to stage.", "error")
    return await app.refresh_with_notice("Component assigned to stage.")


# --- assign an NCRM to a stage --------------------------------------------


async def start_stage_ncrm_ncrm_picker(app: CommandDispatcher, stage_id: str) -> list[str]:
    """Pick an NCRM from the library to assign to the stage with id *stage_id*."""
    entries = await list_ncrm_library(app.env)
    if not entries:
        return ["Add an NCRM first via /library ncrm."]
    items = [ListItem(label=entry.display_name, item_id=str(entry.id)) for entry in entries]
    return app.modal.start_picker(
        "Assign NCRM to stage",
        items,
        lambda item: start_stage_ncrm_role_prompt(app, stage_id, item.item_id),
    )


def start_stage_ncrm_role_prompt(app: CommandDispatcher, stage_id: str, ncrm_id: str) -> list[str]:
    """Prompt for the NCRM role, then create the stage-NCRM link."""
    return app.modal.start_prompt(
        [FieldSpec("role", field_type="select", options=enum_options(NcrmRole))],
        lambda **payload: create_stage_ncrm_link(app, stage_id, ncrm_id, payload),
    )


async def create_stage_ncrm_link(
    app: CommandDispatcher, stage_id: str, ncrm_id: str, payload: dict[str, str | None]
) -> list[str]:
    """Create a stage-NCRM link from a completed role prompt."""
    link = await create_stage_ncrm(
        StageNcrmCreate(
            stage_id=UUID(stage_id),
            ncrm_id=UUID(ncrm_id),
            role=NcrmRole(payload.get("role") or NcrmRole.REAGENT.value),
        ),
        app.env,
    )
    if link is None:
        return await app.refresh_with_notice("Failed to create stage-NCRM link.", "error")
    return await app.refresh_with_notice("Stage-NCRM link created.")


async def create_stage_ncrm_from_prompt(
    app: CommandDispatcher, stage: Stage, ncrm_name: str, payload: dict[str, str | None]
) -> list[str]:
    """Resolve *ncrm_name* and create a stage-NCRM link from a role prompt."""
    ncrm = await get_ncrm_by_display_name(ncrm_name, app.env)
    if ncrm is None:
        return [f"NCRM '{ncrm_name}' not found."]
    link = await create_stage_ncrm(
        StageNcrmCreate(
            stage_id=UUID(str(stage.id)),
            ncrm_id=UUID(str(ncrm.id)),
            role=NcrmRole(payload.get("role") or NcrmRole.REAGENT.value),
        ),
        app.env,
    )
    if link is None:
        return await app.refresh_with_notice("Failed to create stage-NCRM link.", "error")
    return await app.refresh_with_notice("Stage-NCRM link created.")


# --- route-level stage<->component / stage<->NCRM linking ------------------


def start_stage_component_type_prompt(
    app: CommandDispatcher, stage_id: str, component_id: str
) -> list[str]:
    """Prompt for the component type, then create a stage-component link."""
    return app.modal.start_prompt(
        [FieldSpec("component_type", field_type="select", options=COMPONENT_TYPE_OPTIONS)],
        lambda **payload: create_stage_component_link(app, stage_id, component_id, payload),
    )


async def create_stage_component_link(
    app: CommandDispatcher, stage_id: str, component_id: str, payload: dict[str, str | None]
) -> list[str]:
    """Create a stage-component link from a completed type prompt."""
    link = await create_stage_component(
        StageComponentCreate(
            stage_id=UUID(stage_id),
            component_id=UUID(component_id),
            component_type=payload.get("component_type") or "reactant",
        ),
        app.env,
    )
    return ["Stage-component link created."] if link else ["Failed to create stage-component link."]


async def open_component_by_id(app: CommandDispatcher, component_id: str) -> list[str]:
    """Resolve a component id and open its focus screen."""
    component = await get_component_by_id(UUID(component_id), app.env)
    if component is None:
        return ["Component not found."]
    return await app.open_component(component)
