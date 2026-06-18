"""The risk-mode screen: an aggregated risk table for the active scope.

Risk mode is entered from a project, route, stage, or component. It renders that
scope's risks and supports adding (``^A``) and editing (``^E``) them, delegating
the actual add/edit/render work to :mod:`..risk_flows`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from ...operations.component_risks_operations import list_risks_for_component
from ...operations.manufacturing_process_risk_operations import list_risks_for_process
from ...operations.stage_risk_operations import list_risks_for_stage
from .. import lookup, risk_flows, risk_forms
from ..hotkeys import CTRL_A, CTRL_E, CTRL_L
from .base import AppScreen
from .specs import SCREEN_SPECS


class RiskModeScreen(AppScreen):
    """The risk-mode track: render, add, and edit risks for the active scope."""

    key = "risk_mode"
    spec = SCREEN_SPECS["risk_mode"]

    async def render(self) -> list[str]:
        """Render the risk table for the active scope."""
        return await risk_flows.render_risk_mode(self.app)

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Re-render the risk table on ``/list risks``."""
        if verb == "/list" and args and args[0].lower() == "risks":
            return await risk_flows.render_risk_mode(self.app)
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Refresh (``^L``), add a risk (``^A``), or edit one (``^E``)."""
        if key_text == CTRL_L:
            return await risk_flows.render_risk_mode(self.app)
        if key_text == CTRL_A:
            return await self._start_add()
        if key_text == CTRL_E:
            return await self._start_edit()
        return None

    async def _start_add(  # pylint: disable=too-many-return-statements  # one return per risk scope
        self,
    ) -> list[str] | None:
        """Open the add-risk form for the entity in the current risk scope.

        The project scope aggregates risks across every route, so it has no single
        target entity and ignores ``^A``; the process/stage/component scopes each
        attach the new risk to their focused entity.
        """
        scope = self.app.ctx.current.risk_scope
        if scope == "process":
            process = await lookup.current_process(self.app.ctx, self.app.env)
            if process is None:
                return ["Route not found."]
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_process_risk_from_prompt(
                    self.app, process, payload
                ),
                title="Add risk",
            )
        if scope == "stage":
            stage = await lookup.current_stage(self.app.ctx, self.app.env)
            if stage is None:
                return ["Stage not found."]
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_stage_risk_from_prompt(
                    self.app, stage, payload
                ),
                title="Add risk",
            )
        if scope == "component":
            component = await lookup.current_component(self.app.ctx, self.app.env)
            if component is None:
                return ["Component not found."]
            return self.app.modal.start_prompt(
                risk_forms.risk_fields(),
                lambda **payload: risk_flows.create_component_risk_from_prompt(
                    self.app, component, payload
                ),
                title="Add risk",
            )
        return None

    async def _start_edit(  # pylint: disable=too-many-return-statements  # one return per risk scope
        self,
    ) -> list[str] | None:
        """Pick a risk in the current scope and open its pre-filled edit form."""
        scope = self.app.ctx.current.risk_scope
        if scope == "process":
            process = await lookup.current_process(self.app.ctx, self.app.env)
            if process is None:
                return ["Route not found."]
            risks: Sequence[Any] = await list_risks_for_process(UUID(str(process.id)), self.app.env)
            return risk_flows.start_risk_edit_picker(
                self.app, risks, lambda rid: risk_flows.start_process_risk_edit_form(self.app, rid)
            )
        if scope == "stage":
            stage = await lookup.current_stage(self.app.ctx, self.app.env)
            if stage is None:
                return ["Stage not found."]
            risks = await list_risks_for_stage(UUID(str(stage.id)), self.app.env)
            return risk_flows.start_risk_edit_picker(
                self.app, risks, lambda rid: risk_flows.start_stage_risk_edit_form(self.app, rid)
            )
        if scope == "component":
            component = await lookup.current_component(self.app.ctx, self.app.env)
            if component is None:
                return ["Component not found."]
            risks = await list_risks_for_component(UUID(str(component.id)), self.app.env)
            return risk_flows.start_risk_edit_picker(
                self.app,
                risks,
                lambda rid: risk_flows.start_component_risk_edit_form(self.app, rid),
            )
        return None
