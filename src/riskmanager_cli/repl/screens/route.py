"""The route screen: a manufacturing route with add/focus/edit/delete/list flows.

The route screen orchestrates the route's stages and components: it focuses them
(opening the stage/component screens), adds and links them, edits and deletes them
(via :mod:`..entity_flows`), and enters risk mode. Route-level creation and the
chooser/picker chains live here; the shared stage/component mutations live in
:mod:`..entity_flows` and the risk flows in :mod:`..risk_flows`.
"""

from __future__ import annotations

from uuid import UUID

from ...model.tables import ManufacturingProcess
from ...operations.component_operations import (
    component_display_name,
    create_component,
    get_component_by_id,
    list_components_for_process,
)
from ...operations.manufacturing_process_operations import update_manufacturing_process
from ...operations.material_operations import (
    get_material_by_id,
    get_material_by_search,
    list_materials,
)
from ...operations.stage_ncrm_operations import list_ncrms_for_stage
from ...operations.stage_operations import create_stage, list_stages_for_process
from ...repl_engine import ListItem
from ...repl_engine.forms import FieldSpec
from ...schema.create import ComponentCreate, StageCreate
from ...schema.update import ManufacturingProcessUpdate
from .. import entity_flows, lookup, picker_items, risk_flows, risk_forms
from ..context import ContextFrame
from ..form_fields import BOOL_OPTIONS, as_bool, optional_int
from ..hotkeys import CTRL_A, CTRL_E, CTRL_F, CTRL_L, CTRL_R, CTRL_X
from ..renderers.route_renderer import render_route_screen
from .base import AppScreen
from .specs import SCREEN_SPECS


class RouteScreen(AppScreen):
    """The route track: focus/add/edit/delete stages and components, enter risks."""

    key = "route"
    spec = SCREEN_SPECS["route"]

    async def render(self) -> list[str]:
        """Render the route diagram and summary."""
        process = await lookup.current_process(self.app.ctx, self.app.env)
        if process is None:
            return ["Route not found."]
        return await render_route_screen(
            process, self.app.env, width=self.app.screen.width, dim=self.app.screen.dim
        )

    async def run_command(  # pylint: disable=too-many-return-statements,too-many-branches  # one return per command verb
        self, verb: str, args: list[str]
    ) -> list[str] | str | None:
        """Enter risks, focus/list/add/edit/delete/search stages and components."""
        process = await lookup.current_process(self.app.ctx, self.app.env)
        project = await lookup.current_project(self.app.ctx, self.app.env)
        if process is None or project is None:
            return ["Route not found."]
        if verb == "/risks":
            self._enter_risk_mode(process)
            return await self.app.render_current()
        if verb == "/focus" and len(args) >= 2:
            return await self._focus(process, args[0].lower(), " ".join(args[1:]))
        if verb == "/list" and args:
            return await self._handle_route_list(process, args[0].lower())
        if verb == "/add" and args:
            return await self._handle_route_add(process, args)
        if verb == "/edit":
            return await self._handle_route_edit(process, args)
        if verb == "/delete":
            return await self._handle_route_delete(process, args)
        if verb == "/search" and args:
            return await self._search_route(process, " ".join(args))
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def run_hotkey(  # pylint: disable=too-many-return-statements  # one return per hotkey
        self, key_text: str
    ) -> list[str] | str | None:
        """Handle the route hotkeys: add/focus/edit/delete/list/risks."""
        process = await lookup.current_process(self.app.ctx, self.app.env)
        if process is None:
            return ["Route not found."]
        if key_text == CTRL_A:
            return self._start_route_add_chooser(process)
        if key_text == CTRL_F:
            return self._start_route_focus_chooser(process)
        if key_text == CTRL_E:
            return self._start_route_edit_chooser(process)
        if key_text == CTRL_X:
            return self._start_route_delete_chooser(process)
        if key_text == CTRL_L:
            return self._start_route_list_chooser(process)
        if key_text == CTRL_R:
            return await self.run_command("/risks", [])
        return None

    async def search(self, query: str) -> list[str]:
        """Search the route's stages and components by *query*."""
        cleaned = query.strip() or None
        if cleaned is None:
            return await self.app.render_current()
        process = await lookup.current_process(self.app.ctx, self.app.env)
        if process is None:
            return ["Route not found."]
        return await self._search_route(process, cleaned)

    def _enter_risk_mode(self, process: ManufacturingProcess) -> None:
        """Push a process-scoped risk-mode frame onto the navigation stack."""
        self.app.ctx.push(
            ContextFrame(
                track="risk_mode",
                project_id=self.app.ctx.current.project_id,
                project_name=self.app.ctx.current.project_name,
                process_id=str(process.id),
                route_label=self.app.ctx.current.route_label,
                risk_scope="process",
            )
        )
        self.app.session.update_context(
            track="risk_mode",
            project_id=self.app.ctx.current.project_id,
            process_id=str(process.id),
        )

    async def _focus(self, process: ManufacturingProcess, scope: str, name: str) -> list[str]:
        """Focus a stage or component by name."""
        if scope == "stage":
            stage = await lookup.find_stage(self.app.env, process, name)
            if stage is None:
                return [f"Stage '{name}' not found."]
            return await self.app.open_stage(stage)
        if scope == "component":
            component = await lookup.find_component(self.app.env, process, name)
            if component is None:
                return [f"Component '{name}' not found."]
            return await self.app.open_component(component)
        return ["Usage: /focus [stage <name>|component <name>]"]

    # --- add ---------------------------------------------------------------

    def _start_route_add_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "add",
                    field_type="select",
                    options=[
                        ("stage", "stage"),
                        ("component", "component"),
                        ("risk", "risk"),
                        ("component link to stage", "stage-component"),
                        ("NCRM link to stage", "stage-ncrm"),
                    ],
                )
            ],
            lambda **payload: self._route_add_dispatch(process, payload["add"]),
        )

    async def _route_add_dispatch(self, process: ManufacturingProcess, kind: str) -> list[str]:
        if kind == "stage":
            return self.app.modal.start_prompt(
                [FieldSpec("name"), FieldSpec("number", field_type="int")],
                lambda **payload: self._create_stage_from_prompt(process, payload),
                title="Add stage",
            )
        if kind == "component":
            return await self._start_component_add_picker(process)
        if kind == "risk":
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_process_risk_from_prompt(
                    self.app, process, payload
                ),
                title="Add risk",
            )
        if kind == "stage-component":
            return await self._start_stage_component_link_picker(process)
        if kind == "stage-ncrm":
            return await self._start_stage_ncrm_link_picker(process)
        return ["Unknown add option."]

    async def _create_stage_from_prompt(
        self, process: ManufacturingProcess, payload: dict[str, str | None]
    ) -> list[str]:
        created = await create_stage(
            StageCreate(
                process_id=UUID(str(process.id)),
                name=payload.get("name") or "",
                number=optional_int(payload.get("number")) or 0,
            ),
            self.app.env,
        )
        if created is None:
            return await self.app.refresh_with_notice("Failed to create stage.", "error")
        return await self.app.refresh_with_notice(f"Created stage '{created.name}'.")

    async def _start_component_add_picker(self, process: ManufacturingProcess) -> list[str]:
        materials = await list_materials(self.app.env)
        if not materials:
            return ["Add a material first via the library."]
        items = [ListItem(label=material.name, item_id=str(material.id)) for material in materials]
        return self.app.modal.start_picker(
            "Select material for component",
            items,
            lambda item: self._start_component_details_prompt(process, item),
        )

    def _start_component_details_prompt(
        self, process: ManufacturingProcess, material_item: ListItem
    ) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec("control_strategy_role", required=False),
                FieldSpec("is_isolated", field_type="select", options=BOOL_OPTIONS, default="true"),
            ],
            lambda **payload: self._create_component_with_material(
                process, material_item.item_id, payload
            ),
            title="Add component",
        )

    async def _create_component_with_material(
        self, process: ManufacturingProcess, material_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        created = await create_component(
            ComponentCreate(
                process_id=UUID(str(process.id)),
                material_id=UUID(material_id),
                control_strategy_role=payload.get("control_strategy_role"),
                is_isolated=as_bool(payload.get("is_isolated")),
            ),
            self.app.env,
        )
        if created is None:
            return await self.app.refresh_with_notice("Failed to create component.", "error")
        return await self.app.refresh_with_notice("Component created.")

    async def _handle_route_add(  # pylint: disable=too-many-return-statements  # one return per add subject
        self, process: ManufacturingProcess, args: list[str]
    ) -> list[str]:
        subject = args[0].lower()
        if subject == "stage" and "--number" in args and len(args) >= 4:
            number_index = args.index("--number")
            if number_index == 1:
                return ["Stage name is required before --number."]
            stage_name = " ".join(args[1:number_index])
            try:
                number = int(args[number_index + 1])
            except (IndexError, ValueError):
                return ["Usage: /add stage <name> --number N"]
            created = await create_stage(
                StageCreate(process_id=UUID(str(process.id)), name=stage_name, number=number),
                self.app.env,
            )
            if created is None:
                return await self.app.refresh_with_notice("Failed to create stage.", "error")
            return await self.app.refresh_with_notice(f"Created stage '{created.name}'.")
        if subject == "component" and len(args) >= 2:
            material_name = " ".join(args[1:])
            return self.app.modal.start_prompt(
                [
                    FieldSpec("control_strategy_role", required=False),
                    FieldSpec(
                        "is_isolated", field_type="select", options=BOOL_OPTIONS, default="true"
                    ),
                ],
                lambda **payload: self._create_component_from_prompt(
                    process, material_name, payload
                ),
                title="Add component",
            )
        if subject == "risk":
            return await self._start_route_risk_prompt(process, args[1:])
        if subject == "stage-component":
            return await self._start_stage_component_link_picker(process)
        if subject == "stage-ncrm":
            return await self._start_stage_ncrm_link_picker(process)
        return ["Unsupported /add command."]

    async def _create_component_from_prompt(
        self, process: ManufacturingProcess, material_name: str, payload: dict[str, str | None]
    ) -> list[str]:
        material = await get_material_by_search(material_name, self.app.env)
        if material is None:
            return [f"Material '{material_name}' not found."]
        created = await create_component(
            ComponentCreate(
                process_id=UUID(str(process.id)),
                material_id=UUID(str(material.id)),
                control_strategy_role=payload.get("control_strategy_role"),
                is_isolated=as_bool(payload.get("is_isolated")),
            ),
            self.app.env,
        )
        if created is None:
            return await self.app.refresh_with_notice("Failed to create component.", "error")
        return await self.app.refresh_with_notice("Component created.")

    async def _start_route_risk_prompt(
        self, process: ManufacturingProcess, args: list[str]
    ) -> list[str]:
        if not args or args == ["process"]:
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_process_risk_from_prompt(
                    self.app, process, payload
                ),
                title="Add risk",
            )
        if args[0].lower() == "stage" and len(args) >= 2:
            stage_name = " ".join(args[1:])
            stage = await lookup.find_stage(self.app.env, process, stage_name)
            if stage is None:
                return [f"Stage '{stage_name}' not found."]
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_stage_risk_from_prompt(
                    self.app, stage, payload
                ),
                title="Add risk",
            )
        if args[0].lower() == "component" and len(args) >= 2:
            component_name = " ".join(args[1:])
            component = await lookup.find_component(self.app.env, process, component_name)
            if component is None:
                return [f"Component '{component_name}' not found."]
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_component_risk_from_prompt(
                    self.app, component, payload
                ),
                title="Add risk",
            )
        return ["Usage: /add risk [stage <name>|component <name>|process]"]

    # --- focus -------------------------------------------------------------

    def _start_route_focus_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "focus",
                    field_type="select",
                    options=[("stage", "stage"), ("component", "component")],
                )
            ],
            lambda **payload: self._route_focus_dispatch(process, payload["focus"]),
        )

    async def _route_focus_dispatch(self, process: ManufacturingProcess, scope: str) -> list[str]:
        if scope == "stage":
            items = await picker_items.stage_items(self.app.env, process)
            if not items:
                return ["No stages yet."]
            return self.app.modal.start_picker(
                "Focus stage", items, lambda item: self._open_stage_by_id(process, item.item_id)
            )
        items = await picker_items.process_component_items(self.app.env, process)
        if not items:
            return ["No components yet."]
        return self.app.modal.start_picker(
            "Focus component",
            items,
            lambda item: entity_flows.open_component_by_id(self.app, item.item_id),
        )

    async def _open_stage_by_id(self, process: ManufacturingProcess, stage_id: str) -> list[str]:
        for stage in await list_stages_for_process(UUID(str(process.id)), self.app.env):
            if str(stage.id) == stage_id:
                return await self.app.open_stage(stage)
        return ["Stage not found."]

    # --- edit --------------------------------------------------------------

    def _start_route_edit_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "edit",
                    field_type="select",
                    options=[("route", "route"), ("stage", "stage"), ("component", "component")],
                )
            ],
            lambda **payload: self._route_edit_dispatch(process, payload["edit"]),
        )

    def _start_process_edit_form(self, process: ManufacturingProcess) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec("route_number", field_type="int", default=str(process.route_number)),
                FieldSpec("process_number", field_type="int", default=str(process.process_number)),
            ],
            lambda **payload: self._update_process_from_prompt(process, payload),
            title="Edit route",
        )

    async def _update_process_from_prompt(
        self, process: ManufacturingProcess, payload: dict[str, str | None]
    ) -> list[str]:
        updated = await update_manufacturing_process(
            UUID(str(process.id)),
            ManufacturingProcessUpdate(
                route_number=optional_int(payload.get("route_number")),
                process_number=optional_int(payload.get("process_number")),
            ),
            self.app.env,
        )
        if updated is None:
            return await self.app.refresh_with_notice("Failed to update route.", "error")
        self.app.ctx.current.route_label = f"{updated.route_number}.{updated.process_number}"
        self.app.session.update_context(process_id=str(updated.id))
        return await self.app.refresh_with_notice(
            f"Updated route '{updated.route_number}.{updated.process_number}'."
        )

    async def _route_edit_dispatch(self, process: ManufacturingProcess, scope: str) -> list[str]:
        if scope == "route":
            return self._start_process_edit_form(process)
        if scope == "stage":
            items = await picker_items.stage_items(self.app.env, process)
            if not items:
                return ["No stages yet."]
            return self.app.modal.start_picker(
                "Edit stage",
                items,
                lambda item: self._start_stage_edit_form_by_id(process, item.item_id),
            )
        items = await picker_items.process_component_items(self.app.env, process)
        if not items:
            return ["No components yet."]
        return self.app.modal.start_picker(
            "Edit component",
            items,
            lambda item: self._start_component_edit_form_by_id(item.item_id),
        )

    async def _start_stage_edit_form_by_id(
        self, process: ManufacturingProcess, stage_id: str
    ) -> list[str]:
        for stage in await list_stages_for_process(UUID(str(process.id)), self.app.env):
            if str(stage.id) == stage_id:
                return entity_flows.start_stage_edit_form(self.app, stage)
        return ["Stage not found."]

    async def _start_component_edit_form_by_id(self, component_id: str) -> list[str]:
        component = await get_component_by_id(UUID(component_id), self.app.env)
        if component is None:
            return ["Component not found."]
        return entity_flows.start_component_edit_form(self.app, component)

    # --- delete ------------------------------------------------------------

    def _start_route_delete_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "delete",
                    field_type="select",
                    options=[("stage", "stage"), ("component", "component")],
                )
            ],
            lambda **payload: self._route_delete_dispatch(process, payload["delete"]),
        )

    async def _route_delete_dispatch(self, process: ManufacturingProcess, scope: str) -> list[str]:
        if scope == "stage":
            items = await picker_items.stage_items(self.app.env, process)
            if not items:
                return ["No stages yet."]
            return self.app.modal.start_picker(
                "Delete stage",
                items,
                lambda item: self._confirm_delete_stage_by_id(process, item.item_id),
            )
        items = await picker_items.process_component_items(self.app.env, process)
        if not items:
            return ["No components yet."]
        return self.app.modal.start_picker(
            "Delete component",
            items,
            lambda item: self._confirm_delete_component_by_id(item.item_id),
        )

    async def _confirm_delete_stage_by_id(
        self, process: ManufacturingProcess, stage_id: str
    ) -> list[str]:
        for stage in await list_stages_for_process(UUID(str(process.id)), self.app.env):
            if str(stage.id) == stage_id:
                return self.app.start_confirm(
                    f"Delete stage '{stage.name}'",
                    lambda: entity_flows.delete_stage_with_confirmation(
                        self.app, stage, ["--confirm"]
                    ),
                )
        return ["Stage not found."]

    async def _confirm_delete_component_by_id(self, component_id: str) -> list[str]:
        component = await get_component_by_id(UUID(component_id), self.app.env)
        if component is None:
            return ["Component not found."]
        return self.app.start_confirm(
            "Delete component",
            lambda: entity_flows.delete_component_with_confirmation(
                self.app, component, ["--confirm"]
            ),
        )

    async def _handle_route_edit(self, process: ManufacturingProcess, args: list[str]) -> list[str]:
        if len(args) < 2:
            return ["Usage: /edit [stage <name>|component <name>]"]
        scope = args[0].lower()
        name = " ".join(args[1:])
        if scope == "stage":
            stage = await lookup.find_stage(self.app.env, process, name)
            if stage is None:
                return [f"Stage '{name}' not found."]
            return entity_flows.start_stage_edit_form(self.app, stage)
        if scope == "component":
            component = await lookup.find_component(self.app.env, process, name)
            if component is None:
                return [f"Component '{name}' not found."]
            return entity_flows.start_component_edit_form(self.app, component)
        return ["Usage: /edit [stage <name>|component <name>]"]

    async def _handle_route_delete(
        self, process: ManufacturingProcess, args: list[str]
    ) -> list[str]:
        if len(args) < 2:
            return ["Usage: /delete [stage <name>|component <name>] --confirm"]
        scope = args[0].lower()
        name_parts = [part for part in args[1:] if part != "--confirm"]
        confirmed = "--confirm" in args
        name = " ".join(name_parts)
        if scope == "stage":
            stage = await lookup.find_stage(self.app.env, process, name)
            if stage is None:
                return [f"Stage '{name}' not found."]
            return await entity_flows.delete_stage_with_confirmation(
                self.app, stage, ["--confirm"] if confirmed else []
            )
        if scope == "component":
            component = await lookup.find_component(self.app.env, process, name)
            if component is None:
                return [f"Component '{name}' not found."]
            return await entity_flows.delete_component_with_confirmation(
                self.app, component, ["--confirm"] if confirmed else []
            )
        return ["Usage: /delete [stage <name>|component <name>] --confirm"]

    # --- list & search -----------------------------------------------------

    def _start_route_list_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "list",
                    field_type="select",
                    options=[
                        ("stages", "stages"),
                        ("components", "components"),
                        ("risks", "risks"),
                        ("ncrm", "ncrm"),
                    ],
                )
            ],
            lambda **payload: self._handle_route_list(process, payload["list"]),
        )

    async def _handle_route_list(self, process: ManufacturingProcess, kind: str) -> list[str]:
        if kind == "stages":
            stages = await list_stages_for_process(UUID(str(process.id)), self.app.env)
            if not stages:
                return ["Stages", "", "(none)"]
            return ["Stages", "", *[f"{stage.number}. {stage.name}" for stage in stages]]
        if kind == "components":
            return await self._list_components_for_process_lines(process)
        if kind == "risks":
            return await risk_flows.render_process_risks(self.app, process)
        if kind == "ncrm":
            return await self._list_process_ncrm_lines(process)
        return ["Usage: /list stages|components|risks|ncrm"]

    async def _list_components_for_process_lines(self, process: ManufacturingProcess) -> list[str]:
        lines = ["Components", ""]
        components = await list_components_for_process(UUID(str(process.id)), self.app.env)
        if not components:
            return [*lines, "(none)"]
        for component in components:
            label = await component_display_name(component, self.app.env)
            role = component.control_strategy_role or "-"
            lines.append(f"{label} — {role}")
        return lines

    async def _list_process_ncrm_lines(self, process: ManufacturingProcess) -> list[str]:
        lines = ["NCRM links", ""]
        stages = await list_stages_for_process(UUID(str(process.id)), self.app.env)
        found = False
        for stage in stages:
            for link in await list_ncrms_for_stage(UUID(str(stage.id)), self.app.env):
                found = True
                lines.append(f"{stage.name}: {link.role.value} → {link.ncrm_id}")
        return lines if found else [*lines, "(none)"]

    async def _search_route(self, process: ManufacturingProcess, query: str) -> list[str]:
        lowered = query.lower()
        stage_matches = [
            stage
            for stage in await list_stages_for_process(UUID(str(process.id)), self.app.env)
            if lowered in stage.name.lower()
        ]
        component_lines = []
        for component in await list_components_for_process(UUID(str(process.id)), self.app.env):
            material = await get_material_by_id(UUID(str(component.material_id)), self.app.env)
            material_name = material.name if material else str(component.id)
            if lowered in material_name.lower():
                display = await component_display_name(component, self.app.env)
                component_lines.append(f"component: {display}")
        return [
            f"Search results for '{query}'",
            "",
            *[f"stage: {stage.name}" for stage in stage_matches],
            *component_lines,
        ] or [f"No matches for '{query}'."]

    # --- route-level linking -----------------------------------------------

    async def _start_stage_component_link_picker(self, process: ManufacturingProcess) -> list[str]:
        items = await picker_items.stage_items(self.app.env, process)
        if not items:
            return ["Add a stage first with /add stage <name> --number N."]
        return self.app.modal.start_picker(
            "Select stage for component link",
            items,
            lambda item: self._start_stage_component_component_picker(process, item.item_id),
        )

    async def _start_stage_component_component_picker(
        self, process: ManufacturingProcess, stage_id: str
    ) -> list[str]:
        items = await picker_items.process_component_items(self.app.env, process)
        if not items:
            return ["No components yet. Create one with /add component <material>."]
        return self.app.modal.start_picker(
            "Select component to link",
            items,
            lambda item: entity_flows.start_stage_component_type_prompt(
                self.app, stage_id, item.item_id
            ),
        )

    async def _start_stage_ncrm_link_picker(self, process: ManufacturingProcess) -> list[str]:
        items = await picker_items.stage_items(self.app.env, process)
        if not items:
            return ["Add a stage first with /add stage <name> --number N."]
        return self.app.modal.start_picker(
            "Select stage for NCRM link",
            items,
            lambda item: entity_flows.start_stage_ncrm_ncrm_picker(self.app, item.item_id),
        )
