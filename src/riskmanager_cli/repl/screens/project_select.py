"""The project picker: a searchable, navigable list of projects to open."""

from __future__ import annotations

from uuid import UUID

from ...model.enums import TA
from ...model.tables import Project
from ...operations.material_operations import list_materials
from ...operations.project_operations import (
    create_project,
    list_projects,
    search_projects,
)
from ...repl_engine import ListItem
from ...repl_engine.forms import FieldSpec
from ...repl_engine.layout import section_rule, section_width
from ...schema.create import ProjectCreate
from .. import lookup
from ..form_fields import enum_options
from ..hotkeys import CTRL_A
from .base import AppScreen
from .specs import SCREEN_SPECS


class ProjectSelectScreen(AppScreen):
    """The project picker track: open a project by Enter, ``/select``, or ``^A`` add."""

    key = "project_select"
    spec = SCREEN_SPECS["project_select"]

    async def render(self) -> list[str]:
        """Render the (optionally filtered) project pick-list."""
        return await self._render_project_select()

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Open a project by name (``/select``), filter (``/search``), or add one."""
        if verb == "/select" and args:
            query = " ".join(args)
            projects = await search_projects(query, self.app.env)
            if not projects:
                return [f"No project matched '{query}'."]
            return await self.app.open_project(projects[0])
        if verb == "/search" and args:
            return await self._render_project_select(" ".join(args))
        if verb == "/add" and args and args[0].lower() == "project":
            return self.app.modal.start_prompt(
                [
                    FieldSpec("name"),
                    FieldSpec("therapy_area", field_type="select", options=enum_options(TA)),
                ],
                lambda **payload: self._start_project_material_picker(payload),
                title="Add project",
            )
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Open the add-project form on ``^A``."""
        if key_text == CTRL_A:
            return await self.run_command("/add", ["project"])
        return None

    async def activate(self, item: ListItem) -> list[str]:
        """Open the selected project."""
        project = await lookup.project_from_id(self.app.env, item.item_id)
        if project is None:
            return ["Project not found."]
        return await self.app.open_project(project)

    async def search(self, query: str) -> list[str]:
        """Re-render the project list filtered by *query*."""
        return await self._render_project_select(query.strip() or None)

    async def _render_project_select(self, query: str | None = None) -> list[str]:
        projects = await list_projects(self.app.env)
        if query:
            lowered = query.lower()
            projects = [project for project in projects if lowered in project.name.lower()]
        recent_map = {
            project.item_id: project for project in await self._recent_project_items(projects)
        }
        recents = list(recent_map.values())
        all_items = [
            ListItem(label=project.name, item_id=str(project.id))
            for project in projects
            if str(project.id) not in recent_map
        ]
        navigator = self.app.rebuild_navigator(recents, all_items)
        header = [section_rule("Projects", section_width(self.app.screen.width)), ""]
        return [*header, *navigator.render_lines(self.app.screen.width)]

    async def _recent_project_items(self, projects: list[Project]) -> list[ListItem]:
        project_map = {str(project.id): project for project in projects}
        items: list[ListItem] = []
        for project_id in self.app.session.recent_projects:
            project = project_map.get(project_id)
            if project is not None:
                items.append(ListItem(label=project.name, subtitle="(recent)", item_id=project_id))
        return items

    async def _start_project_material_picker(self, payload: dict[str, str | None]) -> list[str]:
        materials = await list_materials(self.app.env)
        if not materials:
            return ["Add a material first via /library materials."]
        items = [ListItem(label=material.name, item_id=str(material.id)) for material in materials]
        name = payload.get("name") or ""
        therapy_area = payload.get("therapy_area") or ""
        return self.app.modal.start_picker(
            f"Select material for project '{name}'",
            items,
            lambda item: self._create_project_from_selection(name, therapy_area, item),
        )

    async def _create_project_from_selection(
        self, name: str, therapy_area: str, material: ListItem
    ) -> list[str]:
        created = await create_project(
            ProjectCreate(
                name=name,
                therapy_area=TA(therapy_area),
                material_id=UUID(material.item_id),
            ),
            self.app.env,
        )
        if created is None:
            return await self.app.refresh_with_notice("Failed to create project.", "error")
        return await self.app.refresh_with_notice(f"Created project '{created.name}'.")
