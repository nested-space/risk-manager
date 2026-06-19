"""Map the navigation context to a screen and service global commands."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from ..config.settings import Environment
from ..model.tables import Component, ManufacturingProcess, Project, Stage
from ..operations.component_operations import (
    component_display_name,
)
from ..repl.renderers.admin_renderer import render_admin_screen
from ..repl_engine.dispatch import (
    Screen,
    ScreenRouter,
    screen_controls,
)
from ..repl_engine.forms import (
    FieldSpec,
    field_key,
)
from ..repl_engine.list_navigator import ListItem, ListNavigator
from ..repl_engine.screen import ScreenManager
from .context import ContextFrame, ContextManager
from .form_fields import (
    CONFIRM_OPTIONS,
    QUIT_OPTIONS,
)
from .hotkeys import (
    CTRL_G,
)
from .screens.admin import AdminScreen
from .screens.base import AppScreen
from .screens.component_focus import ComponentFocusScreen
from .screens.home import HomeScreen
from .screens.library import LibraryDetailScreen, LibraryScreen
from .screens.project import ProjectScreen
from .screens.project_select import ProjectSelectScreen
from .screens.risk_mode import RiskModeScreen
from .screens.route import RouteScreen
from .screens.route_select import RouteSelectScreen
from .screens.specs import DEFAULT_SPEC, SCREEN_SPECS
from .screens.stage_focus import StageFocusScreen
from .session_state import SessionState


class CommandDispatcher(ScreenRouter):  # pylint: disable=too-many-instance-attributes
    """Map the navigation context to a screen and service global commands.

    Subclasses :class:`~..repl_engine.dispatch.ScreenRouter`, which owns the
    generic dispatch plumbing (command parsing, modal/notice/tab state, and the
    capability/legend surface). This class supplies the application specifics:
    which :class:`~..repl_engine.dispatch.Screen` is active, the global commands
    and hotkeys, the status-bar header, and the quit-confirmation flow.

    Each screen is a cohesive :class:`~.screens.base.AppScreen` under
    ``repl/screens/``; this class holds the registry and the cross-screen
    navigation entry points (``open_*``/``enter_*``) the screens call.
    """

    def __init__(
        self,
        ctx: ContextManager,
        session: SessionState,
        screen: ScreenManager,
        env: Environment,
    ) -> None:
        """Create a dispatcher bound to the active REPL state.

        Args:
            ctx: Navigation context manager.
            session: Persistent session-state helper.
            screen: Screen manager for width-aware list rendering.
            env: Active database environment.
        """
        super().__init__(screen)
        self.ctx = ctx
        self.session = session
        self.env = env
        self.navigator: ListNavigator | None = None
        self._quit_requested = False
        # The screen registry, keyed by screen key (see current_screen_key). The
        # single library screen serves both the home and list views (keyed by
        # sub-mode); every other key maps to its own screen.
        library = LibraryScreen(self)
        self._screens: dict[str, Screen] = {
            "home": HomeScreen(self),
            "admin": AdminScreen(self),
            "project_select": ProjectSelectScreen(self),
            "project": ProjectScreen(self),
            "route_select": RouteSelectScreen(self),
            "route": RouteScreen(self),
            "stage_focus": StageFocusScreen(self),
            "component_focus": ComponentFocusScreen(self),
            "risk_mode": RiskModeScreen(self),
            "library_home": library,
            "library_list": library,
            "library_detail": LibraryDetailScreen(self),
        }
        # Capability-less default for any unrecognised screen key (its spec is the
        # engine default: no navigation/search/actions, just "^C back").
        self._fallback = AppScreen(self)

    @property
    def quit_requested(self) -> bool:
        """Return ``True`` once the home-screen quit confirmation is accepted.

        The REPL loop polls this to break out of its event loop; routing the
        quit through the standard prompt machinery (rather than a sentinel
        return value) keeps :meth:`submit_prompt_selection` returning plain
        lines like every other prompt.
        """
        return self._quit_requested

    def active_screen(self) -> Screen:
        """Return the screen matching the current navigation context.

        Maps the current screen key (see :meth:`current_screen_key`) to its
        registered :class:`~..repl_engine.dispatch.Screen`, falling back to a
        capability-less default screen for any unrecognised key.
        """
        return self._screens.get(self.current_screen_key(), self._fallback)

    def header(self) -> tuple[str, str]:
        """Return the status-bar header as ``(left, right)`` text.

        The engine's screen draws these verbatim; the navigation breadcrumb is
        left-aligned and the mode label right-aligned.
        """
        return self.ctx.breadcrumb(), self.ctx.mode_label()

    async def pop_context(self) -> list[str] | None:
        """Pop one navigation level and re-render, or signal nothing to leave.

        Returns:
            The re-rendered screen lines after popping, or ``None`` when the
            stack is already at its root (the caller decides whether that means
            "quit").
        """
        if self.ctx.pop() is None:
            return None
        lines = await self.render_current()
        self._sync_session()
        return lines

    def _sync_session(self) -> None:
        """Persist the active navigation context for restore on next launch."""
        current = self.ctx.current
        self.session.update_context(
            track=current.track,
            project_id=current.project_id,
            process_id=current.process_id,
            stage_id=current.stage_id,
            component_id=current.component_id,
        )

    def after_navigation(self) -> None:
        """Persist navigation after any command/hotkey/activation (router hook)."""
        self._sync_session()

    async def dispatch_global(  # pylint: disable=too-many-return-statements  # one return per global command
        self, verb: str, args: list[str]
    ) -> list[str] | str | None:
        """Service commands available on every screen, or defer with ``None``."""
        if verb == "/quit":
            return "__QUIT__"
        if verb == "/home":
            self.ctx.reset()
            self.navigator = None
            self._sync_session()
            return await self.render_current()
        if verb == "/help":
            return self._help_lines(args[0] if args else None)
        if verb == "/admin":
            if args:
                return await self._screens["admin"].run_command(verb, args)
            if self.ctx.current.track != "home":
                return ["/admin is only available from home."]
            return self.enter_admin()
        return None

    async def hotkey_global(self, key_text: str) -> list[str] | str | None:
        """Service the home hotkey (``^G``), or defer with ``None``."""
        if key_text == CTRL_G and self.ctx.current.track != "home":
            return await self.dispatch_global("/home", [])
        return None

    def enter_admin(self) -> list[str]:
        """Push the admin track and render it."""
        self.ctx.push(ContextFrame(track="admin"))
        self.session.update_context(track="admin")
        return render_admin_screen()

    async def enter_project_select(self) -> list[str]:
        """Push the project-picker track and render it."""
        self.ctx.push(ContextFrame(track="project_select"))
        self.navigator = None
        self.session.update_context(track="project_select")
        return await self.render_current()

    async def enter_library(self, sub_mode: str) -> list[str]:
        """Push the library track for *sub_mode* and render it.

        Args:
            sub_mode: One of ``materials``/``ncrm``/``counterions``/``select``.
        """
        self.ctx.push(ContextFrame(track="library", library_sub=sub_mode))
        self.session.update_context(track="library")
        return await self.render_current()

    def push_library_detail(self, sub_mode: str, item_id: str) -> None:
        """Push a library-detail frame for the entry *item_id* in *sub_mode*.

        The library screen calls this when Enter opens a row's detail page, so the
        navigation context (owned here) stays the dispatcher's responsibility.
        """
        self.ctx.push(
            ContextFrame(
                track="library_detail",
                library_sub=sub_mode,
                library_detail_id=item_id,
            )
        )

    def start_confirm(self, label: str, on_yes: Callable[[], Any]) -> list[str]:
        """Open a No/Yes confirmation prompt that runs *on_yes* when confirmed.

        Args:
            label: Prompt label (e.g. ``"Delete stage 'Coupling'"``).
            on_yes: Zero-argument callable run on confirmation; may be async.

        Returns:
            Initial prompt-render lines.
        """
        return self.modal.start_prompt(
            [FieldSpec(label, field_type="select", options=CONFIRM_OPTIONS, default="no")],
            lambda **payload: self._resolve_confirm(payload[field_key(label)], on_yes),
        )

    async def _resolve_confirm(self, answer: str | None, on_yes: Callable[[], Any]) -> list[str]:
        if answer != "yes":
            return await self.refresh_with_notice("Cancelled.", "warning")
        result = on_yes()
        if inspect.isawaitable(result):
            return self._coerce_lines(await result)
        return self._coerce_lines(result)

    def start_quit_confirm(self) -> list[str]:
        """Open the home-screen ``Quit?`` confirmation, defaulting to ``Yes``.

        Accepting sets :attr:`quit_requested` (which the REPL loop polls to exit);
        declining re-renders the landing screen.
        """
        return self.modal.start_prompt(
            [FieldSpec("Quit?", field_type="select", options=QUIT_OPTIONS, default="yes")],
            lambda **payload: self._resolve_quit(payload[field_key("Quit?")]),
        )

    async def _resolve_quit(self, answer: str | None) -> list[str]:
        if answer == "yes":
            self._quit_requested = True
        return await self.render_current()

    # ------------------------------------------------------------------ #
    # Search and help legend
    # ------------------------------------------------------------------ #

    def current_screen_key(self) -> str:
        """Return the registry key for the current screen.

        Most tracks map to their own name. The ``library`` track is split by
        sub-mode so its landing page and list views can expose different
        capabilities and hints (see :data:`SCREEN_SPECS`).
        """
        track = self.ctx.current.track
        if track == "library":
            if (self.ctx.current.library_sub or "select") == "select":
                return "library_home"
            return "library_list"
        return track

    def rebuild_navigator(
        self, recents: list[ListItem], all_items: list[ListItem]
    ) -> ListNavigator:
        """Rebuild the list navigator, preserving the current selection by id.

        The arrow-key loop re-renders the active list screen after every key
        press, which rebuilds the navigator. Carrying the previously selected
        item id forward keeps the cursor where the user moved it instead of
        snapping back to the first item.

        Args:
            recents: Recently used items for the new navigator.
            all_items: Full set of items for the new navigator.

        Returns:
            The freshly built navigator, also stored on ``self``.
        """
        previous = self.navigator
        previous_id = (
            previous.selected.item_id
            if previous is not None and previous.selected is not None
            else None
        )
        navigator = ListNavigator(recents, all_items)
        if previous_id:
            navigator.select_item_id(previous_id)
        self.navigator = navigator
        return navigator

    async def open_project(self, project: Project) -> list[str]:
        """Push the project track for *project* and render its screen."""
        self.ctx.push(
            ContextFrame(track="project", project_id=str(project.id), project_name=project.name)
        )
        self.navigator = None
        self.session.push_project(str(project.id))
        self._sync_session()
        return await self.render_current()

    async def open_route(self, project: Project, process: ManufacturingProcess) -> list[str]:
        """Push the route track for *process* and render its screen."""
        label = f"{process.route_number}.{process.process_number}"
        self.ctx.push(
            ContextFrame(
                track="route",
                project_id=str(project.id),
                project_name=project.name,
                process_id=str(process.id),
                route_label=label,
            )
        )
        self.navigator = None
        self.session.push_route(str(project.id), str(process.id))
        self.session.update_context(
            track="route",
            project_id=str(project.id),
            process_id=str(process.id),
            stage_id=None,
            component_id=None,
        )
        return await self.render_current()

    async def open_stage(self, stage: Stage) -> list[str]:
        """Push the stage-focus track for *stage* and render its screen."""
        self.ctx.push(
            ContextFrame(
                track="stage_focus",
                project_id=self.ctx.current.project_id,
                project_name=self.ctx.current.project_name,
                process_id=self.ctx.current.process_id,
                route_label=self.ctx.current.route_label,
                stage_id=str(stage.id),
                stage_name=stage.name,
            )
        )
        self.session.update_context(track="stage_focus", stage_id=str(stage.id))
        return await self.render_current()

    async def open_component(self, component: Component) -> list[str]:
        """Push the component-focus track for *component* and render its screen."""
        self.ctx.push(
            ContextFrame(
                track="component_focus",
                project_id=self.ctx.current.project_id,
                project_name=self.ctx.current.project_name,
                process_id=self.ctx.current.process_id,
                route_label=self.ctx.current.route_label,
                component_id=str(component.id),
                component_name=await component_display_name(component, self.env),
            )
        )
        self.session.update_context(track="component_focus", component_id=str(component.id))
        return await self.render_current()

    def pop_focus_to_parent(self) -> None:
        """Leave a focused stage/component screen after its entity was deleted.

        The current frame still references the now-deleted entity, so re-rendering
        it would fail; pop back to the parent (route) screen and re-sync session
        context before refreshing.
        """
        if self.ctx.current.track in {"stage_focus", "component_focus"}:
            self.ctx.pop()
            self._sync_session()

    def _help_lines(self, topic: str | None) -> list[str]:
        if topic is not None:
            spec = SCREEN_SPECS.get(topic)
            if spec is None:
                return [f"Help for {topic}", "", "No detailed help available."]
            return [f"Help for {topic}", "", *screen_controls(spec)]
        key = self.current_screen_key()
        spec = SCREEN_SPECS.get(key, DEFAULT_SPEC)
        return [f"Help · {key}", "", *screen_controls(spec)]

    @staticmethod
    def _coerce_lines(result: Any) -> list[str]:
        if isinstance(result, list) and all(isinstance(item, str) for item in result):
            return result
        if isinstance(result, str):
            return [result]
        return [str(result)]
