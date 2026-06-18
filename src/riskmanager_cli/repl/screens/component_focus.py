"""The component-focus screen: a component's sections plus salt/risk actions."""

from __future__ import annotations

from uuid import UUID

from ...model.tables import Component
from ...operations.component_operations import component_display_name
from ...operations.component_risks_operations import delete_component_risk
from ...operations.component_salt_operations import (
    create_component_salt,
    delete_component_salt,
)
from ...operations.counterion_operations import list_counterions
from ...operations.material_operations import get_material_by_id
from ...repl_engine import ListItem
from ...repl_engine.forms import FieldSpec
from ...schema.create import ComponentSaltCreate
from .. import entity_flows, lookup, risk_flows
from ..context import ContextFrame
from ..form_fields import OPTIONAL_BOOL_OPTIONS, optional_bool, optional_float
from ..hotkeys import CTRL_A, CTRL_E, CTRL_R, CTRL_U, CTRL_X
from ..renderers.component_renderer import (
    component_targets,
    gather_component_sections,
    render_component_screen,
)
from .focus_base import FocusScreen
from .specs import SCREEN_SPECS


class ComponentFocusScreen(FocusScreen):
    """The component-focus track: edit/delete the component, assign salts, edit risks."""

    key = "component_focus"
    spec = SCREEN_SPECS["component_focus"]

    async def render(self) -> list[str]:
        """Render the component's sections with a caret over its rows."""
        component = await lookup.current_component(self.app.ctx, self.app.env)
        if component is None:
            return ["Component not found."]
        material = await get_material_by_id(UUID(str(component.material_id)), self.app.env)
        sections = await gather_component_sections(component, material, self.app.env)
        display_name = await component_display_name(component, self.app.env)
        navigator = self.app.rebuild_navigator([], component_targets(sections))
        selected_id = navigator.selected.item_id if navigator.selected is not None else None
        return render_component_screen(
            sections,
            display_name=display_name,
            width=self.app.screen.width,
            selected_id=selected_id,
        )

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Assign a salt (``/add salt``), edit/delete the component, or enter risks."""
        component = await lookup.current_component(self.app.ctx, self.app.env)
        if component is None:
            return ["Component not found."]
        if verb == "/add" and args and args[0].lower() == "salt":
            return await self._start_salt_picker(component)
        if verb == "/edit":
            return entity_flows.start_component_edit_form(self.app, component)
        if verb == "/delete":
            return await entity_flows.delete_component_with_confirmation(self.app, component, args)
        if verb == "/risks":
            self._enter_risk_mode(component)
            return await self.app.render_current()
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def run_hotkey(  # pylint: disable=too-many-return-statements  # one return per hotkey
        self, key_text: str
    ) -> list[str] | str | None:
        """Handle the component hotkeys: salt/edit/unassign/delete/risks."""
        component = await lookup.current_component(self.app.ctx, self.app.env)
        if component is None:
            return ["Component not found."]
        if key_text == CTRL_A:
            return await self._start_salt_picker(component)
        if key_text == CTRL_E:
            return entity_flows.start_component_edit_form(self.app, component)
        if key_text == CTRL_U:
            return await self._start_component_row_unassign()
        if key_text == CTRL_X:
            return self.app.start_confirm(
                "Delete component",
                lambda: entity_flows.delete_component_with_confirmation(
                    self.app, component, ["--confirm"]
                ),
            )
        if key_text == CTRL_R:
            self._enter_risk_mode(component)
            return await self.app.render_current()
        return None

    async def activate(self, item: ListItem) -> list[str]:
        """Open the caret-selected row.

        Only risk rows are selectable for an action; Enter opens an inline edit
        form. Salt rows are selectable only so they can be unassigned (``^U``).
        """
        kind, _, raw_id = item.item_id.partition(":")
        if kind == "risk":
            return await risk_flows.start_component_risk_edit_form(self.app, raw_id)
        return await self.app.render_current()

    def _enter_risk_mode(self, component: Component) -> None:
        """Push a component-scoped risk-mode frame onto the navigation stack."""
        self.app.ctx.push(
            ContextFrame(
                track="risk_mode",
                project_id=self.app.ctx.current.project_id,
                project_name=self.app.ctx.current.project_name,
                process_id=self.app.ctx.current.process_id,
                route_label=self.app.ctx.current.route_label,
                component_id=str(component.id),
                component_name=self.app.ctx.current.component_name,
                risk_scope="component",
            )
        )
        self.app.session.update_context(track="risk_mode", component_id=str(component.id))

    async def _start_salt_picker(self, component: Component) -> list[str]:
        counterions = await list_counterions(self.app.env)
        if not counterions:
            return ["Add a counterion first via /library counterions."]
        items = [
            ListItem(label=counterion.name, item_id=str(counterion.id))
            for counterion in counterions
        ]
        return self.app.modal.start_picker(
            "Select counterion for salt",
            items,
            lambda item: self._start_salt_details_prompt(component, item),
        )

    def _start_salt_details_prompt(self, component: Component, counterion: ListItem) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec("stoichiometry", field_type="float", required=False),
                FieldSpec(
                    "is_fully_defined",
                    field_type="select",
                    options=OPTIONAL_BOOL_OPTIONS,
                    default="",
                    required=False,
                ),
            ],
            lambda **payload: self._create_component_salt_from_prompt(
                component, counterion.item_id, payload
            ),
            title="Assign salt",
        )

    async def _create_component_salt_from_prompt(
        self, component: Component, counterion_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        created = await create_component_salt(
            ComponentSaltCreate(
                component_id=UUID(str(component.id)),
                counterion_id=UUID(counterion_id),
                stoichiometry=optional_float(payload.get("stoichiometry")),
                is_fully_defined=optional_bool(payload.get("is_fully_defined")),
            ),
            self.app.env,
        )
        if created is None:
            return await self.app.refresh_with_notice("Failed to create salt record.", "error")
        return await self.app.refresh_with_notice("Created salt record.")

    async def _start_component_row_unassign(self) -> list[str]:
        """Confirm-and-delete the caret-selected salt or risk row.

        ``^X`` deletes the component itself; this removes a single section row.
        """
        navigator = self.list_navigator
        selected = navigator.selected if navigator is not None else None
        if selected is None:
            return await self.app.refresh_with_notice("Nothing selected.", "warning")
        kind, _, raw_id = selected.item_id.partition(":")
        if kind == "salt":
            return self.app.start_confirm(
                f"Unassign salt {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_component_salt(UUID(raw_id), self.app.env), "Salt unassigned."
                ),
            )
        if kind == "risk":
            return self.app.start_confirm(
                f"Delete risk '{selected.label}'",
                lambda: self._unassign_with_notice(
                    delete_component_risk(UUID(raw_id), self.app.env), "Risk deleted."
                ),
            )
        return await self.app.refresh_with_notice("Nothing to unassign.", "warning")
