"""The route picker: a searchable, navigable list of a project's routes."""

from __future__ import annotations

from uuid import UUID

from ...operations.manufacturing_process_operations import list_processes_for_project
from ...repl_engine import ListItem
from .. import lookup
from .base import AppScreen
from .specs import SCREEN_SPECS


class RouteSelectScreen(AppScreen):
    """The route picker track: open a route by Enter, ``/route``, or ``/`` search."""

    key = "route_select"
    spec = SCREEN_SPECS["route_select"]

    async def render(self) -> list[str]:
        """Render the (optionally filtered) route pick-list."""
        return await self._render_route_select()

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Filter the routes (``/search``) or open one by label (``/route``)."""
        if verb == "/search" and args:
            return await self._render_route_select(" ".join(args))
        if verb == "/route" and args:
            project = await lookup.current_project(self.app.ctx, self.app.env)
            if project is None:
                return ["Project not found."]
            process = await lookup.process_from_route_label(self.app.env, str(project.id), args[0])
            if process is None:
                return [f"Route '{args[0]}' not found."]
            return await self.app.open_route(project, process)
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def activate(self, item: ListItem) -> list[str]:
        """Open the selected route."""
        process = await lookup.process_from_id(self.app.env, item.item_id)
        project = await lookup.current_project(self.app.ctx, self.app.env)
        if process is None or project is None:
            return ["Route not found."]
        return await self.app.open_route(project, process)

    async def search(self, query: str) -> list[str]:
        """Re-render the route list filtered by *query*."""
        return await self._render_route_select(query.strip() or None)

    async def _render_route_select(self, query: str | None = None) -> list[str]:
        project = await lookup.current_project(self.app.ctx, self.app.env)
        if project is None:
            return ["Project not found."]
        processes = await list_processes_for_project(UUID(str(project.id)), self.app.env)
        if query:
            lowered = query.lower()
            processes = [
                process
                for process in processes
                if lowered in f"{process.route_number}.{process.process_number}".lower()
            ]
        recent_ids = self.app.session.recent_routes.get(str(project.id), [])
        recent_lookup = {
            str(process.id): ListItem(
                label=f"{process.route_number}.{process.process_number}",
                item_id=str(process.id),
            )
            for process in processes
            if str(process.id) in recent_ids
        }
        recents = [recent_lookup[route_id] for route_id in recent_ids if route_id in recent_lookup]
        all_items = [
            ListItem(
                label=f"{process.route_number}.{process.process_number}",
                item_id=str(process.id),
            )
            for process in processes
            if str(process.id) not in recent_lookup
        ]
        navigator = self.app.rebuild_navigator(recents, all_items)
        return [
            f"Routes for {project.name}",
            "",
            *navigator.render_lines(self.app.screen.width),
        ]
