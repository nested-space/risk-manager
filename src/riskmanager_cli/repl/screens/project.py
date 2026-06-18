"""The project screen: a project's routes pick-list plus add/edit/risks actions."""

from __future__ import annotations

from uuid import UUID

from ...model.enums import TA
from ...model.tables import ManufacturingProcess, Project
from ...operations.manufacturing_process_operations import (
    create_manufacturing_process,
    list_processes_for_project,
)
from ...operations.project_operations import update_project
from ...repl_engine import ListItem
from ...repl_engine.forms import FieldSpec
from ...schema.create import ManufacturingProcessCreate
from ...schema.update import ProjectUpdate
from .. import lookup
from ..context import ContextFrame
from ..form_fields import enum_options
from ..hotkeys import CTRL_A, CTRL_E, CTRL_R, CTRL_T
from ..renderers.project_renderer import render_project_screen
from .base import AppScreen
from .specs import SCREEN_SPECS


class ProjectScreen(AppScreen):
    """The project track: open routes, enter risk mode, add a process, or edit."""

    key = "project"
    spec = SCREEN_SPECS["project"]

    async def render(self) -> list[str]:
        """Render the project screen with its navigable routes pick-list."""
        project = await lookup.current_project(self.app.ctx, self.app.env)
        if project is None:
            return ["Project not found."]
        return await self._render_project(project)

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Open a route (``/route``), enter risk mode (``/risks``), or add a process."""
        project = await lookup.current_project(self.app.ctx, self.app.env)
        if project is None:
            return ["Project not found."]
        if verb == "/route":
            return await self._open_or_pick_route(project, args)
        if verb == "/risks":
            self.app.ctx.push(
                ContextFrame(
                    track="risk_mode",
                    project_id=str(project.id),
                    project_name=project.name,
                    risk_scope="project",
                )
            )
            self.app.session.update_context(track="risk_mode", project_id=str(project.id))
            return await self.app.render_current()
        if verb == "/add" and args and args[0].lower() == "process":
            return self.app.modal.start_prompt(
                [
                    FieldSpec("route_number", field_type="int"),
                    FieldSpec("process_number", field_type="int"),
                ],
                lambda **payload: self._create_manufacturing_process_from_prompt(project, payload),
                title="Add process",
            )
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Routes (``^T``), risks (``^R``), add process (``^A``), edit (``^E``)."""
        if key_text == CTRL_T:
            return await self.run_command("/route", [])
        if key_text == CTRL_R:
            return await self.run_command("/risks", [])
        if key_text == CTRL_A:
            return await self.run_command("/add", ["process"])
        if key_text == CTRL_E:
            project = await lookup.current_project(self.app.ctx, self.app.env)
            if project is None:
                return ["Project not found."]
            return self._start_project_edit_form(project)
        return None

    async def activate(self, item: ListItem) -> list[str]:
        """Open the selected route."""
        process = await lookup.process_from_id(self.app.env, item.item_id)
        project = await lookup.current_project(self.app.ctx, self.app.env)
        if process is None or project is None:
            return ["Route not found."]
        return await self.app.open_route(project, process)

    async def _open_or_pick_route(self, project: Project, args: list[str]) -> list[str]:
        """Open a route by label, or push the route picker when no label is given."""
        if not args:
            self.app.ctx.push(
                ContextFrame(
                    track="route_select",
                    project_id=str(project.id),
                    project_name=project.name,
                )
            )
            self.app.session.update_context(track="route_select", project_id=str(project.id))
            return await self.app.render_current()
        process = await lookup.process_from_route_label(self.app.env, str(project.id), args[0])
        if process is None:
            return [f"Route '{args[0]}' not found."]
        return await self.app.open_route(project, process)

    async def _render_project(self, project: Project) -> list[str]:
        """Render the project screen with a navigable routes pick-list.

        The project's manufacturing processes are shown as a list navigator so
        routes can be opened inline with the arrow keys and Enter, the same way
        projects are opened from the home screen.
        """
        processes = await list_processes_for_project(UUID(str(project.id)), self.app.env)
        recent_ids = self.app.session.recent_routes.get(str(project.id), [])

        def label(process: ManufacturingProcess) -> str:
            return f"Route {process.route_number} Process {process.process_number}"

        recent_lookup = {
            str(process.id): ListItem(label=label(process), item_id=str(process.id))
            for process in processes
            if str(process.id) in recent_ids
        }
        recents = [recent_lookup[route_id] for route_id in recent_ids if route_id in recent_lookup]
        all_items = [
            ListItem(label=label(process), item_id=str(process.id))
            for process in processes
            if str(process.id) not in recent_lookup
        ]
        navigator = self.app.rebuild_navigator(recents, all_items)
        route_lines = navigator.render_lines(self.app.screen.width)
        return await render_project_screen(
            project, self.app.env, route_lines=route_lines, width=self.app.screen.width
        )

    def _start_project_edit_form(self, project: Project) -> list[str]:
        return self.app.modal.start_prompt(
            [
                FieldSpec("name", default=project.name),
                FieldSpec(
                    "therapy_area",
                    field_type="select",
                    options=enum_options(TA),
                    default=project.therapy_area.value,
                ),
            ],
            lambda **payload: self._update_project_from_prompt(project, payload),
            title="Edit project",
        )

    async def _update_project_from_prompt(
        self, project: Project, payload: dict[str, str | None]
    ) -> list[str]:
        therapy_area = payload.get("therapy_area")
        updated = await update_project(
            UUID(str(project.id)),
            ProjectUpdate(
                name=payload.get("name") or None,
                therapy_area=TA(therapy_area) if therapy_area else None,
            ),
            self.app.env,
        )
        if updated is None:
            return await self.app.refresh_with_notice("Failed to update project.", "error")
        self.app.ctx.current.project_name = updated.name
        self.app.session.update_context(project_id=str(updated.id))
        return await self.app.refresh_with_notice(f"Updated project '{updated.name}'.")

    async def _create_manufacturing_process_from_prompt(
        self, project: Project, payload: dict[str, str | None]
    ) -> list[str]:
        route_number = int(payload.get("route_number") or 0)
        process_number = int(payload.get("process_number") or 0)
        if route_number < 1 or process_number < 1:
            return ["Route and process numbers must be 1 or greater."]
        created = await create_manufacturing_process(
            ManufacturingProcessCreate(
                project_id=UUID(str(project.id)),
                route_number=route_number,
                process_number=process_number,
            ),
            self.app.env,
        )
        if created is None:
            return await self.app.refresh_with_notice("Failed to create process.", "error")
        return await self.app.refresh_with_notice(
            f"Created process {created.route_number}.{created.process_number}."
        )
