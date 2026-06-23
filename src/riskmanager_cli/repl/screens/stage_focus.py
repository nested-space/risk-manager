"""The stage-focus screen: a stage's sections plus add/assign/edit/risk actions."""

from __future__ import annotations

from uuid import UUID

from ...model.enums import NcrmRole
from ...model.tables import ManufacturingProcess, Stage
from ...operations.component_operations import component_display_name, get_component_by_id
from ...operations.material_operations import get_material_by_id
from ...operations.ncrm_library_operations import get_ncrm_by_id
from ...operations.stage_component_operations import (
    delete_stage_component,
    list_stage_components,
)
from ...operations.stage_ncrm_operations import delete_stage_ncrm, list_ncrms_for_stage
from ...operations.stage_risk_operations import delete_stage_risk
from ...repl_engine import ListItem
from ...repl_engine.forms import FieldSpec
from .. import entity_flows, lookup, picker_items, risk_flows, risk_forms
from ..context import ContextFrame
from ..form_fields import enum_options
from ..hotkeys import CTRL_A, CTRL_E, CTRL_K, CTRL_L, CTRL_R, CTRL_U, CTRL_X
from ..renderers.stage_renderer import (
    gather_stage_sections,
    render_stage_screen,
    stage_targets,
)
from .focus_base import FocusScreen
from .specs import SCREEN_SPECS


class StageFocusScreen(FocusScreen):
    """The stage-focus track: add risks/NCRMs/components, edit/delete, enter risks."""

    key = "stage_focus"
    spec = SCREEN_SPECS["stage_focus"]

    async def render(self) -> list[str]:
        """Render the stage's sections with a caret over its rows."""
        stage = await lookup.current_stage(self.app.ctx, self.app.env)
        if stage is None:
            return ["Stage not found."]
        sections = await gather_stage_sections(stage, self.app.env)
        navigator = self.app.rebuild_navigator([], stage_targets(sections))
        selected_id = navigator.selected.item_id if navigator.selected is not None else None
        return render_stage_screen(
            stage, sections, width=self.app.screen.width, selected_id=selected_id
        )

    async def run_command(  # pylint: disable=too-many-return-statements  # one return per command verb
        self, verb: str, args: list[str]
    ) -> list[str] | str | None:
        """Add/assign rows, list, edit/delete the stage, or enter risk mode."""
        stage = await lookup.current_stage(self.app.ctx, self.app.env)
        process = await lookup.current_process(self.app.ctx, self.app.env)
        if stage is None or process is None:
            return ["Stage not found."]
        if verb == "/risks":
            self._enter_risk_mode(stage)
            return await self.app.render_current()
        if verb == "/add" and args:
            handled = await self._handle_add(stage, process, args)
            if handled is not None:
                return handled
        if verb == "/assign" and args and args[0].lower() == "component":
            return await entity_flows.start_stage_component_picker(self.app, stage, process)
        if verb == "/list" and args:
            return await self._handle_stage_list(stage, args[0].lower())
        if verb == "/edit":
            return entity_flows.start_stage_edit_form(self.app, stage)
        if verb == "/delete":
            return await entity_flows.delete_stage_with_confirmation(self.app, stage, args)
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _handle_add(
        self, stage: Stage, process: ManufacturingProcess, args: list[str]
    ) -> list[str] | None:
        """Service ``/add risk|ncrm|component``; ``None`` if the subject is unknown."""
        subject = args[0].lower()
        if subject == "risk":
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_stage_risk_from_prompt(
                    self.app, stage, payload
                ),
                title="Add risk",
            )
        if subject == "ncrm" and len(args) >= 2:
            ncrm_name = " ".join(args[1:])
            return self.app.modal.start_prompt(
                [FieldSpec("role", field_type="select", options=enum_options(NcrmRole))],
                lambda **payload: entity_flows.create_stage_ncrm_from_prompt(
                    self.app, stage, ncrm_name, payload
                ),
            )
        if subject == "component":
            # Components are created at the route level; in a stage we only assign
            # an existing process component. /add component aliases /assign component.
            return await entity_flows.start_stage_component_picker(self.app, stage, process)
        return None

    async def run_hotkey(  # pylint: disable=too-many-return-statements  # one return per hotkey
        self, key_text: str
    ) -> list[str] | str | None:
        """Handle the stage hotkeys: add/list/edit/risks/unassign/delete."""
        stage = await lookup.current_stage(self.app.ctx, self.app.env)
        process = await lookup.current_process(self.app.ctx, self.app.env)
        if stage is None or process is None:
            return ["Stage not found."]
        if key_text == CTRL_A:
            return self._start_stage_add_chooser(stage, process)
        if key_text == CTRL_L:
            return self._start_stage_list_chooser(stage)
        if key_text == CTRL_E:
            return entity_flows.start_stage_edit_form(self.app, stage)
        if key_text == CTRL_R:
            return await self.run_command("/risks", [])
        if key_text == CTRL_U:
            return await self._start_stage_row_unassign(stage)
        if key_text == CTRL_X:
            return self.app.start_confirm(
                f"Delete stage '{stage.name}'",
                lambda: entity_flows.delete_stage_with_confirmation(self.app, stage, ["--confirm"]),
            )
        if key_text == CTRL_K:
            molecule = await self._selected_row_molecule(stage)
            if molecule is None:
                return await self.app.refresh_with_notice("No molecule selected.", "warning")
            return await self.show_structure_notice(*molecule)
        return None

    async def _selected_row_molecule(self, stage: Stage) -> tuple[str, str | None] | None:
        """Resolve the caret-selected row to its ``(name, smiles)``.

        Component rows resolve through their material; NCRM rows through their
        library entry. Risk rows (and an empty selection) carry no molecule and
        return ``None``.
        """
        navigator = self.list_navigator
        selected = navigator.selected if navigator is not None else None
        if selected is None:
            return None
        kind, _, raw_id = selected.item_id.partition(":")
        if kind == "component":
            component = await get_component_by_id(UUID(raw_id), self.app.env)
            if component is None:
                return None
            material = await get_material_by_id(UUID(str(component.material_id)), self.app.env)
            return None if material is None else (material.name, material.smiles)
        if kind == "ncrm":
            links = await list_ncrms_for_stage(UUID(str(stage.id)), self.app.env)
            link = next((link for link in links if str(link.id) == raw_id), None)
            if link is None:
                return None
            ncrm = await get_ncrm_by_id(UUID(str(link.ncrm_id)), self.app.env)
            return None if ncrm is None else (ncrm.display_name, ncrm.smiles)
        return None

    async def activate(self, item: ListItem) -> list[str]:
        """Open the caret-selected stage row.

        Components push the component-focus screen onto the stage frame; NCRMs and
        risks open an inline edit form. Either way the user stays on the stage.
        """
        kind, _, raw_id = item.item_id.partition(":")
        if kind == "component":
            return await entity_flows.open_component_by_id(self.app, raw_id)
        if kind == "ncrm":
            return await entity_flows.start_stage_ncrm_edit_form(self.app, raw_id)
        if kind == "risk":
            return await risk_flows.start_stage_risk_edit_form(self.app, raw_id)
        return await self.app.render_current()

    def _enter_risk_mode(self, stage: Stage) -> None:
        """Push a stage-scoped risk-mode frame onto the navigation stack."""
        self.app.ctx.push(
            ContextFrame(
                track="risk_mode",
                project_id=self.app.ctx.current.project_id,
                project_name=self.app.ctx.current.project_name,
                process_id=self.app.ctx.current.process_id,
                route_label=self.app.ctx.current.route_label,
                stage_id=str(stage.id),
                stage_name=self.app.ctx.current.stage_name,
                risk_scope="stage",
            )
        )
        self.app.session.update_context(track="risk_mode", stage_id=str(stage.id))

    def _start_stage_add_chooser(self, stage: Stage, process: ManufacturingProcess) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "add",
                    field_type="select",
                    options=[("risk", "risk"), ("NCRM", "ncrm"), ("component", "component")],
                )
            ],
            lambda **payload: self._stage_add_dispatch(stage, process, payload["add"]),
        )

    async def _stage_add_dispatch(
        self, stage: Stage, process: ManufacturingProcess, kind: str
    ) -> list[str]:
        if kind == "risk":
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_stage_risk_from_prompt(
                    self.app, stage, payload
                ),
                title="Add risk",
            )
        if kind == "ncrm":
            return await entity_flows.start_stage_ncrm_ncrm_picker(self.app, str(stage.id))
        return await entity_flows.start_stage_component_picker(self.app, stage, process)

    def _start_stage_list_chooser(self, stage: Stage) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "list",
                    field_type="select",
                    options=[("risks", "risks"), ("components", "components"), ("ncrm", "ncrm")],
                )
            ],
            lambda **payload: self._handle_stage_list(stage, payload["list"]),
        )

    async def _handle_stage_list(self, stage: Stage, kind: str) -> list[str]:
        if kind == "risks":
            return await risk_flows.render_stage_risks(self.app, stage)
        if kind == "components":
            component_links = await list_stage_components(UUID(str(stage.id)), self.app.env)
            if not component_links:
                return ["Stage components", "", "(none)"]
            lines = ["Stage components", ""]
            for link in component_links:
                component = await get_component_by_id(UUID(str(link.component_id)), self.app.env)
                name = str(link.component_id)
                if component is not None:
                    name = await component_display_name(component, self.app.env)
                lines.append(f"{link.component_type}: {name}")
            return lines
        if kind == "ncrm":
            ncrm_links = await list_ncrms_for_stage(UUID(str(stage.id)), self.app.env)
            if not ncrm_links:
                return ["Stage NCRM", "", "(none)"]
            return [
                "Stage NCRM",
                "",
                *[f"{link.role.value}: {link.ncrm_id}" for link in ncrm_links],
            ]
        return ["Usage: /list risks|components|ncrm"]

    async def _start_stage_row_unassign(self, stage: Stage) -> list[str]:
        """Confirm-and-unassign the caret-selected component/NCRM/risk row.

        Unlike ``^X`` (which deletes the whole stage), this removes a single
        section row and keeps the user on the stage. Component rows carry the
        component id, so the stage-component *link* id is resolved here.
        """
        navigator = self.list_navigator
        selected = navigator.selected if navigator is not None else None
        if selected is None:
            return await self.app.refresh_with_notice("Nothing selected.", "warning")
        kind, _, raw_id = selected.item_id.partition(":")
        if kind == "component":
            link_id = await picker_items.stage_component_link_id(self.app.env, stage, raw_id)
            if link_id is None:
                return await self.app.refresh_with_notice("Component not found.", "error")
            return self.app.start_confirm(
                f"Unassign {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_stage_component(link_id, self.app.env), "Component unassigned."
                ),
            )
        if kind == "ncrm":
            return self.app.start_confirm(
                f"Unassign {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_stage_ncrm(UUID(raw_id), self.app.env), "NCRM unassigned."
                ),
            )
        if kind == "risk":
            return self.app.start_confirm(
                f"Delete risk '{selected.label}'",
                lambda: self._unassign_with_notice(
                    delete_stage_risk(UUID(raw_id), self.app.env), "Risk deleted."
                ),
            )
        return await self.app.refresh_with_notice("Nothing to unassign.", "warning")
