"""Slash-command parsing and dispatch for the riskmanager CLI REPL."""
# pylint: disable=too-many-lines  # all 40+ command handlers live here intentionally; splitting would break cohesion

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import UUID

from ..config.settings import Environment
from ..model.enums import NcrmRole
from ..model.severity import LEVEL_OPTIONS
from ..model.tables import Component, ManufacturingProcess, Project, Stage
from ..operations.component_operations import (
    component_display_name,
    create_component,
    delete_component,
    get_component_by_id,
    list_components_for_process,
    update_component,
)
from ..operations.component_risks_operations import (
    create_component_risk,
    delete_component_risk,
    list_risks_for_component,
    update_component_risk,
)
from ..operations.component_salt_operations import (
    create_component_salt,
    delete_component_salt,
)
from ..operations.counterion_operations import (
    list_counterions,
)
from ..operations.manufacturing_process_operations import (
    list_processes_for_project,
    update_manufacturing_process,
)
from ..operations.manufacturing_process_risk_operations import (
    create_manufacturing_process_risk,
    list_risks_for_process,
    update_manufacturing_process_risk,
)
from ..operations.material_operations import (
    get_material_by_id,
    get_material_by_search,
    list_materials,
)
from ..operations.ncrm_library_operations import (
    get_ncrm_by_display_name,
    list_ncrm_library,
)
from ..operations.stage_component_operations import (
    create_stage_component,
    delete_stage_component,
    list_stage_components,
)
from ..operations.stage_ncrm_operations import (
    create_stage_ncrm,
    delete_stage_ncrm,
    list_ncrms_for_stage,
    update_stage_ncrm,
)
from ..operations.stage_operations import (
    create_stage,
    delete_stage,
    list_stages_for_process,
    update_stage,
)
from ..operations.stage_risk_operations import (
    create_stage_risk,
    delete_stage_risk,
    list_risks_for_stage,
    update_stage_risk,
)
from ..repl.renderers.admin_renderer import render_admin_screen
from ..repl.renderers.component_renderer import (
    component_targets,
    gather_component_sections,
    render_component_screen,
)
from ..repl.renderers.risk_renderer import render_risk_table
from ..repl.renderers.route_renderer import render_route_screen
from ..repl.renderers.stage_renderer import (
    gather_stage_sections,
    render_stage_screen,
    stage_targets,
)
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
from ..schema.create import (
    ComponentCreate,
    ComponentRiskCreate,
    ComponentSaltCreate,
    ManufacturingProcessRiskCreate,
    StageComponentCreate,
    StageCreate,
    StageNcrmCreate,
    StageRiskCreate,
)
from ..schema.update import (
    ComponentRiskUpdate,
    ComponentUpdate,
    ManufacturingProcessRiskUpdate,
    ManufacturingProcessUpdate,
    StageNcrmUpdate,
    StageRiskUpdate,
    StageUpdate,
)
from . import lookup
from .context import ContextFrame, ContextManager
from .form_fields import (
    BOOL_OPTIONS,
    COMPONENT_TYPE_OPTIONS,
    CONFIRM_OPTIONS,
    OPTIONAL_BOOL_OPTIONS,
    QUIT_OPTIONS,
    as_bool,
    default_text,
    enum_options,
    optional_bool,
    optional_float,
    optional_int,
)
from .hotkeys import (
    CTRL_A,
    CTRL_E,
    CTRL_F,
    CTRL_G,
    CTRL_L,
    CTRL_R,
    CTRL_U,
    CTRL_X,
)
from .screens.admin import AdminScreen
from .screens.home import HomeScreen
from .screens.legacy import LegacyScreen
from .screens.library import LibraryDetailScreen, LibraryScreen
from .screens.project import ProjectScreen
from .screens.project_select import ProjectSelectScreen
from .screens.route_select import RouteSelectScreen
from .screens.specs import DEFAULT_SPEC, SCREEN_SPECS
from .session_state import SessionState


class CommandDispatcher(ScreenRouter):  # pylint: disable=too-many-instance-attributes
    """Map the navigation context to a screen and service global commands.

    Subclasses :class:`~..repl_engine.dispatch.ScreenRouter`, which owns the
    generic dispatch plumbing (command parsing, modal/notice/tab state, and the
    capability/legend surface). This class supplies the application specifics:
    which :class:`~..repl_engine.dispatch.Screen` is active, the global commands
    and hotkeys, the status-bar header, and the quit-confirmation flow.

    Screens not yet extracted into ``repl/screens/`` are served by
    :class:`~.screens.legacy.LegacyScreen`, which routes engine calls back to the
    ``_dispatch_<track>``/``_hotkey_<track>``/``_render_*`` methods still defined
    here.
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
        # Screens already extracted into repl/screens/; everything else falls
        # back to a LegacyScreen adapter (see active_screen). The single library
        # screen serves both the home and list views (keyed by sub-mode).
        library = LibraryScreen(self)
        self._screens: dict[str, Screen] = {
            "home": HomeScreen(self),
            "admin": AdminScreen(self),
            "project_select": ProjectSelectScreen(self),
            "project": ProjectScreen(self),
            "route_select": RouteSelectScreen(self),
            "library_home": library,
            "library_list": library,
            "library_detail": LibraryDetailScreen(self),
        }

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

        Extracted screens come from :attr:`_screens`; the rest are served by a
        :class:`~.screens.legacy.LegacyScreen` adapter keyed on the current
        screen, which routes engine calls back to the ``_dispatch_<track>`` /
        ``_hotkey_<track>`` / ``_render_*`` methods still defined here.
        """
        key = self.current_screen_key()
        screen = self._screens.get(key)
        if screen is not None:
            return screen
        spec = SCREEN_SPECS.get(key, DEFAULT_SPEC)
        return LegacyScreen(self, key, self.ctx.current.track, spec)

    async def activate_selection(  # pylint: disable=too-many-return-statements,too-many-branches  # one return per list-driven track
        self, item: ListItem
    ) -> list[str]:
        """Open the currently selected list item for list-driven screens.

        Args:
            item: Selected list item.

        Returns:
            Rendered lines for the activated screen.
        """
        if self.ctx.current.track == "stage_focus":
            return await self._activate_stage_row(item.item_id)
        if self.ctx.current.track == "component_focus":
            return await self._activate_component_row(item.item_id)
        return await self.render_current()

    async def _activate_component_row(self, item_id: str) -> list[str]:
        """Open the caret-selected component row by its ``"{kind}:{uuid}"`` id.

        Only risk rows are selectable; Enter opens an inline edit form that
        re-renders the component screen on completion.
        """
        kind, _, raw_id = item_id.partition(":")
        if kind == "risk":
            return await self._start_component_risk_edit_form(raw_id)
        # Salt rows are selectable only so they can be unassigned (^U); Enter is a
        # no-op because there is no salt edit form.
        return await self.render_current()

    async def _activate_stage_row(self, item_id: str) -> list[str]:
        """Open the caret-selected stage row by its ``"{kind}:{uuid}"`` id.

        Components push the component-focus screen onto the stage frame, so
        leaving them (Esc/Ctrl-C) returns to the stage rather than the route.
        NCRMs and risks open an inline edit form that re-renders the stage on
        completion, so they too keep the user on the stage.
        """
        kind, _, raw_id = item_id.partition(":")
        if kind == "component":
            return await self._open_component_by_id(raw_id)
        if kind == "ncrm":
            return await self._start_stage_ncrm_edit_form(raw_id)
        if kind == "risk":
            return await self._start_stage_risk_edit_form(raw_id)
        return await self.render_current()

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

    async def render_screen(  # pylint: disable=too-many-return-statements,too-many-branches  # one render path per navigation track
        self,
    ) -> list[str]:
        """Render the screen matching the current navigation context.

        The :class:`~.screens.legacy.LegacyScreen` adapter calls this for screens
        not yet extracted into ``repl/screens/``.
        """
        track = self.ctx.current.track
        if track == "route":
            process = await lookup.current_process(self.ctx, self.env)
            if process is None:
                return ["Route not found."]
            return await render_route_screen(
                process, self.env, width=self.screen.width, dim=self.screen.dim
            )
        if track == "stage_focus":
            return await self._render_stage_focus()
        if track == "component_focus":
            return await self._render_component_focus()
        if track == "risk_mode":
            return await self._render_risk_mode()
        return ["Home"]

    async def dispatch_global(  # pylint: disable=too-many-return-statements  # one return per global command
        self, verb: str, args: list[str]
    ) -> list[str] | str | None:
        """Service commands available on every screen, or defer with ``None``."""
        if verb == "/quit":
            return "__QUIT__"
        if verb == "/home":
            self.ctx.reset()
            self.navigator = None
            self.session.update_context(
                track="home",
                project_id=None,
                process_id=None,
                stage_id=None,
                component_id=None,
            )
            return await self.render_current()
        if verb == "/help":
            return self._help_lines(args[0] if args else None)
        if verb == "/admin" and not args:
            if self.ctx.current.track != "home":
                return ["/admin is only available from home."]
            return self.enter_admin()
        if verb == "/admin" and args:
            return await self._screens["admin"].run_command(verb, args)
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

    async def _dispatch_route(  # pylint: disable=too-many-return-statements  # one return per command verb
        self, verb: str, args: list[str]
    ) -> list[str]:
        process = await lookup.current_process(self.ctx, self.env)
        project = await lookup.current_project(self.ctx, self.env)
        if process is None or project is None:
            return ["Route not found."]
        if verb == "/risks":
            self.ctx.push(
                ContextFrame(
                    track="risk_mode",
                    project_id=str(project.id),
                    project_name=project.name,
                    process_id=str(process.id),
                    route_label=self.ctx.current.route_label,
                    risk_scope="process",
                )
            )
            self.session.update_context(
                track="risk_mode",
                project_id=str(project.id),
                process_id=str(process.id),
            )
            return await self._render_process_risks(process)
        if verb == "/focus" and len(args) >= 2:
            scope = args[0].lower()
            target_name = " ".join(args[1:])
            if scope == "stage":
                stage = await lookup.find_stage(self.env, process, target_name)
                if stage is None:
                    return [f"Stage '{target_name}' not found."]
                return await self._open_stage(stage)
            if scope == "component":
                component = await lookup.find_component(self.env, process, target_name)
                if component is None:
                    return [f"Component '{target_name}' not found."]
                return await self._open_component(component)
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

    async def _dispatch_stage_focus(  # pylint: disable=too-many-return-statements  # one return per command verb
        self, verb: str, args: list[str]
    ) -> list[str]:
        stage = await lookup.current_stage(self.ctx, self.env)
        process = await lookup.current_process(self.ctx, self.env)
        if stage is None or process is None:
            return ["Stage not found."]
        if verb == "/risks":
            self.ctx.push(
                ContextFrame(
                    track="risk_mode",
                    project_id=self.ctx.current.project_id,
                    project_name=self.ctx.current.project_name,
                    process_id=self.ctx.current.process_id,
                    route_label=self.ctx.current.route_label,
                    stage_id=str(stage.id),
                    stage_name=self.ctx.current.stage_name,
                    risk_scope="stage",
                )
            )
            self.session.update_context(track="risk_mode", stage_id=str(stage.id))
            return await self._render_stage_risks(stage)
        if verb == "/add" and args:
            if args[0].lower() == "risk":
                return self.modal.start_prompt(
                    self._risk_fields(),
                    lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                    title="Add risk",
                )
            if args[0].lower() == "ncrm" and len(args) >= 2:
                ncrm_name = " ".join(args[1:])
                return self.modal.start_prompt(
                    [
                        FieldSpec(
                            "role",
                            field_type="select",
                            options=enum_options(NcrmRole),
                        )
                    ],
                    lambda **payload: self._create_stage_ncrm_from_prompt(
                        stage,
                        ncrm_name,
                        payload,
                    ),
                )
            if args[0].lower() == "component":
                # Components are created at the route level; in a stage we only
                # assign an existing process component. /add component is kept as
                # a muscle-memory alias for /assign component.
                return await self._start_stage_component_picker(stage, process)
        if verb == "/assign" and args and args[0].lower() == "component":
            return await self._start_stage_component_picker(stage, process)
        if verb == "/list" and args:
            return await self._handle_stage_list(stage, args[0].lower())
        if verb == "/edit":
            return self._start_stage_edit_form(stage)
        if verb == "/delete":
            return await self._delete_stage_with_confirmation(stage, args)
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _dispatch_component_focus(self, verb: str, args: list[str]) -> list[str]:
        component = await lookup.current_component(self.ctx, self.env)
        if component is None:
            return ["Component not found."]
        if verb == "/add" and args and args[0].lower() == "salt":
            return await self._start_salt_picker(component)
        if verb == "/edit":
            return self._start_component_edit_form(component)
        if verb == "/delete":
            return await self._delete_component_with_confirmation(component, args)
        if verb == "/risks":
            self.ctx.push(
                ContextFrame(
                    track="risk_mode",
                    project_id=self.ctx.current.project_id,
                    project_name=self.ctx.current.project_name,
                    process_id=self.ctx.current.process_id,
                    route_label=self.ctx.current.route_label,
                    component_id=str(component.id),
                    component_name=self.ctx.current.component_name,
                    risk_scope="component",
                )
            )
            self.session.update_context(track="risk_mode", component_id=str(component.id))
            return await self._render_component_risks(component)
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _dispatch_risk_mode(self, verb: str, args: list[str]) -> list[str]:
        if verb == "/list" and args and args[0].lower() == "risks":
            return await self._render_risk_mode()
        return [f"Unknown command: {verb}. Type /help for commands."]

    # ------------------------------------------------------------------ #
    # Hotkey dispatch
    #
    # Commands are driven by Ctrl-<letter> hotkeys instead of typed slash
    # commands. The engine routes each keystroke to the active screen's
    # ``run_hotkey``; LegacyScreen forwards that to the matching
    # ``_hotkey_<track>`` handler below. No-argument actions reuse the existing
    # ``_dispatch_*`` handlers, while argument-bearing actions open a
    # chooser/form/picker chain that ends in the same leaf handlers the slash
    # commands use.
    # ------------------------------------------------------------------ #

    async def _hotkey_route(  # pylint: disable=too-many-return-statements  # one return per route hotkey
        self, key: str
    ) -> list[str] | None:
        process = await lookup.current_process(self.ctx, self.env)
        if process is None:
            return ["Route not found."]
        if key == CTRL_A:
            return self._start_route_add_chooser(process)
        if key == CTRL_F:
            return self._start_route_focus_chooser(process)
        if key == CTRL_E:
            return self._start_route_edit_chooser(process)
        if key == CTRL_X:
            return self._start_route_delete_chooser(process)
        if key == CTRL_L:
            return self._start_route_list_chooser(process)
        if key == CTRL_R:
            return await self._dispatch_route("/risks", [])
        return None

    async def _hotkey_stage_focus(  # pylint: disable=too-many-return-statements  # one return per stage hotkey
        self, key: str
    ) -> list[str] | None:
        stage = await lookup.current_stage(self.ctx, self.env)
        process = await lookup.current_process(self.ctx, self.env)
        if stage is None or process is None:
            return ["Stage not found."]
        if key == CTRL_A:
            return self._start_stage_add_chooser(stage, process)
        if key == CTRL_L:
            return self._start_stage_list_chooser(stage)
        if key == CTRL_E:
            return self._start_stage_edit_form(stage)
        if key == CTRL_R:
            return await self._dispatch_stage_focus("/risks", [])
        if key == CTRL_U:
            return await self._start_stage_row_unassign(stage)
        if key == CTRL_X:
            return self.start_confirm(
                f"Delete stage '{stage.name}'",
                lambda: self._delete_stage_with_confirmation(stage, ["--confirm"]),
            )
        return None

    async def _hotkey_component_focus(  # pylint: disable=too-many-return-statements  # one return per component hotkey
        self, key: str
    ) -> list[str] | None:
        component = await lookup.current_component(self.ctx, self.env)
        if component is None:
            return ["Component not found."]
        if key == CTRL_A:
            return await self._start_salt_picker(component)
        if key == CTRL_E:
            return self._start_component_edit_form(component)
        if key == CTRL_U:
            return await self._start_component_row_unassign(component)
        if key == CTRL_X:
            return self.start_confirm(
                "Delete component",
                lambda: self._delete_component_with_confirmation(component, ["--confirm"]),
            )
        if key == CTRL_R:
            return await self._dispatch_component_focus("/risks", [])
        return None

    async def _hotkey_risk_mode(self, key: str) -> list[str] | None:
        if key == CTRL_L:
            return await self._dispatch_risk_mode("/list", ["risks"])
        if key == CTRL_A:
            return await self._start_risk_mode_add()
        if key == CTRL_E:
            return await self._start_risk_mode_edit()
        return None

    async def _start_risk_mode_add(  # pylint: disable=too-many-return-statements  # one return per risk scope
        self,
    ) -> list[str] | None:
        """Open the add-risk form for the entity in the current risk scope.

        The project scope aggregates risks across every route, so it has no single
        target entity and ignores ``^A``; the process/stage/component scopes each
        attach the new risk to their focused entity.
        """
        scope = self.ctx.current.risk_scope
        if scope == "process":
            process = await lookup.current_process(self.ctx, self.env)
            if process is None:
                return ["Route not found."]
            return self.modal.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_process_risk_from_prompt(process, payload),
                title="Add risk",
            )
        if scope == "stage":
            stage = await lookup.current_stage(self.ctx, self.env)
            if stage is None:
                return ["Stage not found."]
            return self.modal.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                title="Add risk",
            )
        if scope == "component":
            component = await lookup.current_component(self.ctx, self.env)
            if component is None:
                return ["Component not found."]
            return self.modal.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_component_risk_from_prompt(component, payload),
                title="Add risk",
            )
        return None

    async def _start_risk_mode_edit(  # pylint: disable=too-many-return-statements  # one return per risk scope
        self,
    ) -> list[str] | None:
        """Pick a risk in the current scope and open its pre-filled edit form."""
        scope = self.ctx.current.risk_scope
        if scope == "process":
            process = await lookup.current_process(self.ctx, self.env)
            if process is None:
                return ["Route not found."]
            process_risks = await list_risks_for_process(UUID(str(process.id)), self.env)
            return self._start_risk_edit_picker(process_risks, self._start_process_risk_edit_form)
        if scope == "stage":
            stage = await lookup.current_stage(self.ctx, self.env)
            if stage is None:
                return ["Stage not found."]
            stage_risks = await list_risks_for_stage(UUID(str(stage.id)), self.env)
            return self._start_risk_edit_picker(stage_risks, self._start_stage_risk_edit_form)
        if scope == "component":
            component = await lookup.current_component(self.ctx, self.env)
            if component is None:
                return ["Component not found."]
            component_risks = await list_risks_for_component(UUID(str(component.id)), self.env)
            return self._start_risk_edit_picker(
                component_risks, self._start_component_risk_edit_form
            )
        return None

    def _start_risk_edit_picker(
        self,
        risks: Sequence[Any],
        open_edit: Callable[[str], Any],
    ) -> list[str]:
        """Show a picker over *risks* that opens *open_edit* for the chosen id."""
        if not risks:
            return ["No risks yet."]
        items = [
            ListItem(label=f"{risk.risk_type} · {risk.name}", item_id=str(risk.id))
            for risk in risks
        ]
        return self.modal.start_picker("Edit risk", items, lambda item: open_edit(item.item_id))

    # ------------------------------------------------------------------ #
    # Chooser, picker, and confirmation chains
    # ------------------------------------------------------------------ #

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

    def _start_route_add_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.modal.start_prompt(
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
            return self.modal.start_prompt(
                [FieldSpec("name"), FieldSpec("number", field_type="int")],
                lambda **payload: self._create_stage_from_prompt(process, payload),
                title="Add stage",
            )
        if kind == "component":
            return await self._start_component_add_picker(process)
        if kind == "risk":
            return self.modal.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_process_risk_from_prompt(process, payload),
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
            self.env,
        )
        if created is None:
            return await self.refresh_with_notice("Failed to create stage.", "error")
        return await self.refresh_with_notice(f"Created stage '{created.name}'.")

    async def _start_component_add_picker(self, process: ManufacturingProcess) -> list[str]:
        materials = await list_materials(self.env)
        if not materials:
            return ["Add a material first via the library."]
        items = [ListItem(label=material.name, item_id=str(material.id)) for material in materials]
        return self.modal.start_picker(
            "Select material for component",
            items,
            lambda item: self._start_component_details_prompt(process, item),
        )

    def _start_component_details_prompt(
        self, process: ManufacturingProcess, material_item: ListItem
    ) -> list[str]:
        return self.modal.start_prompt(
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
            self.env,
        )
        if created is None:
            return await self.refresh_with_notice("Failed to create component.", "error")
        return await self.refresh_with_notice("Component created.")

    def _start_route_focus_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.modal.start_prompt(
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
            items = await self._stage_items(process)
            if not items:
                return ["No stages yet."]
            return self.modal.start_picker(
                "Focus stage",
                items,
                lambda item: self._open_stage_by_id(process, item.item_id),
            )
        items = await self._process_component_items(process)
        if not items:
            return ["No components yet."]
        return self.modal.start_picker(
            "Focus component",
            items,
            lambda item: self._open_component_by_id(item.item_id),
        )

    async def _open_stage_by_id(self, process: ManufacturingProcess, stage_id: str) -> list[str]:
        for stage in await list_stages_for_process(UUID(str(process.id)), self.env):
            if str(stage.id) == stage_id:
                return await self._open_stage(stage)
        return ["Stage not found."]

    async def _open_component_by_id(self, component_id: str) -> list[str]:
        component = await get_component_by_id(UUID(component_id), self.env)
        if component is None:
            return ["Component not found."]
        return await self._open_component(component)

    def _start_route_edit_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.modal.start_prompt(
            [
                FieldSpec(
                    "edit",
                    field_type="select",
                    options=[
                        ("route", "route"),
                        ("stage", "stage"),
                        ("component", "component"),
                    ],
                )
            ],
            lambda **payload: self._route_edit_dispatch(process, payload["edit"]),
        )

    def _start_process_edit_form(self, process: ManufacturingProcess) -> list[str]:
        return self.modal.start_prompt(
            [
                FieldSpec("route_number", field_type="int", default=str(process.route_number)),
                FieldSpec("process_number", field_type="int", default=str(process.process_number)),
            ],
            lambda **payload: self._update_process_from_prompt(process, payload),
            title="Edit route",
        )

    async def _route_edit_dispatch(self, process: ManufacturingProcess, scope: str) -> list[str]:
        if scope == "route":
            return self._start_process_edit_form(process)
        if scope == "stage":
            items = await self._stage_items(process)
            if not items:
                return ["No stages yet."]
            return self.modal.start_picker(
                "Edit stage",
                items,
                lambda item: self._start_stage_edit_form_by_id(process, item.item_id),
            )
        items = await self._process_component_items(process)
        if not items:
            return ["No components yet."]
        return self.modal.start_picker(
            "Edit component",
            items,
            lambda item: self._start_component_edit_form_by_id(item.item_id),
        )

    async def _start_stage_edit_form_by_id(
        self, process: ManufacturingProcess, stage_id: str
    ) -> list[str]:
        for stage in await list_stages_for_process(UUID(str(process.id)), self.env):
            if str(stage.id) == stage_id:
                return self._start_stage_edit_form(stage)
        return ["Stage not found."]

    def _start_stage_edit_form(self, stage: Stage) -> list[str]:
        return self.modal.start_prompt(
            [
                FieldSpec("name", default=stage.name),
                FieldSpec("number", field_type="int", default=str(stage.number)),
            ],
            lambda **payload: self._update_stage_from_prompt(stage, payload),
            title="Edit stage",
        )

    async def _start_stage_ncrm_edit_form(self, link_id: str) -> list[str]:
        """Open a role-edit form for the stage-NCRM link with id *link_id*."""
        stage = await lookup.current_stage(self.ctx, self.env)
        if stage is None:
            return ["Stage not found."]
        link = next(
            (
                candidate
                for candidate in await list_ncrms_for_stage(UUID(str(stage.id)), self.env)
                if str(candidate.id) == link_id
            ),
            None,
        )
        if link is None:
            return ["NCRM link not found."]
        return self.modal.start_prompt(
            [
                FieldSpec(
                    "role",
                    field_type="select",
                    options=enum_options(NcrmRole),
                    default=link.role.value,
                )
            ],
            lambda **payload: self._update_stage_ncrm_from_prompt(link_id, payload),
        )

    async def _start_stage_risk_edit_form(self, risk_id: str) -> list[str]:
        """Open an edit form for the stage risk with id *risk_id*."""
        stage = await lookup.current_stage(self.ctx, self.env)
        if stage is None:
            return ["Stage not found."]
        risk = next(
            (
                candidate
                for candidate in await list_risks_for_stage(UUID(str(stage.id)), self.env)
                if str(candidate.id) == risk_id
            ),
            None,
        )
        if risk is None:
            return ["Risk not found."]
        return self.modal.start_prompt(
            self._risk_edit_fields(risk),
            lambda **payload: self._update_stage_risk_from_prompt(risk_id, payload),
            title="Edit risk",
        )

    async def _start_process_risk_edit_form(self, risk_id: str) -> list[str]:
        """Open an edit form for the process risk with id *risk_id*."""
        process = await lookup.current_process(self.ctx, self.env)
        if process is None:
            return ["Route not found."]
        risk = next(
            (
                candidate
                for candidate in await list_risks_for_process(UUID(str(process.id)), self.env)
                if str(candidate.id) == risk_id
            ),
            None,
        )
        if risk is None:
            return ["Risk not found."]
        return self.modal.start_prompt(
            self._risk_edit_fields(risk),
            lambda **payload: self._update_process_risk_from_prompt(risk_id, payload),
            title="Edit risk",
        )

    async def _start_component_risk_edit_form(self, risk_id: str) -> list[str]:
        """Open an edit form for the component risk with id *risk_id*."""
        component = await lookup.current_component(self.ctx, self.env)
        if component is None:
            return ["Component not found."]
        risk = next(
            (
                candidate
                for candidate in await list_risks_for_component(UUID(str(component.id)), self.env)
                if str(candidate.id) == risk_id
            ),
            None,
        )
        if risk is None:
            return ["Risk not found."]
        return self.modal.start_prompt(
            self._risk_edit_fields(risk),
            lambda **payload: self._update_component_risk_from_prompt(risk_id, payload),
            title="Edit risk",
        )

    async def _start_component_edit_form_by_id(self, component_id: str) -> list[str]:
        component = await get_component_by_id(UUID(component_id), self.env)
        if component is None:
            return ["Component not found."]
        return self._start_component_edit_form(component)

    def _start_component_edit_form(self, component: Component) -> list[str]:
        return self.modal.start_prompt(
            [
                FieldSpec(
                    "control_strategy_role",
                    required=False,
                    default=component.control_strategy_role,
                ),
                FieldSpec(
                    "is_isolated",
                    field_type="select",
                    options=BOOL_OPTIONS,
                    default="true" if component.is_isolated else "false",
                ),
            ],
            lambda **payload: self._update_component_from_prompt(component, payload),
            title="Edit component",
        )

    def _start_route_delete_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.modal.start_prompt(
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
            items = await self._stage_items(process)
            if not items:
                return ["No stages yet."]
            return self.modal.start_picker(
                "Delete stage",
                items,
                lambda item: self._confirm_delete_stage_by_id(process, item.item_id),
            )
        items = await self._process_component_items(process)
        if not items:
            return ["No components yet."]
        return self.modal.start_picker(
            "Delete component",
            items,
            lambda item: self._confirm_delete_component_by_id(item.item_id),
        )

    async def _confirm_delete_stage_by_id(
        self, process: ManufacturingProcess, stage_id: str
    ) -> list[str]:
        for stage in await list_stages_for_process(UUID(str(process.id)), self.env):
            if str(stage.id) == stage_id:
                return self.start_confirm(
                    f"Delete stage '{stage.name}'",
                    lambda: self._delete_stage_with_confirmation(stage, ["--confirm"]),
                )
        return ["Stage not found."]

    async def _confirm_delete_component_by_id(self, component_id: str) -> list[str]:
        component = await get_component_by_id(UUID(component_id), self.env)
        if component is None:
            return ["Component not found."]
        return self.start_confirm(
            "Delete component",
            lambda: self._delete_component_with_confirmation(component, ["--confirm"]),
        )

    def _start_route_list_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.modal.start_prompt(
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

    def _start_stage_add_chooser(self, stage: Stage, process: ManufacturingProcess) -> list[str]:
        return self.modal.start_prompt(
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
            return self.modal.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                title="Add risk",
            )
        if kind == "ncrm":
            return await self._start_stage_ncrm_ncrm_picker(str(stage.id))
        return await self._start_stage_component_picker(stage, process)

    def _start_stage_list_chooser(self, stage: Stage) -> list[str]:
        return self.modal.start_prompt(
            [
                FieldSpec(
                    "list",
                    field_type="select",
                    options=[
                        ("risks", "risks"),
                        ("components", "components"),
                        ("ncrm", "ncrm"),
                    ],
                )
            ],
            lambda **payload: self._handle_stage_list(stage, payload["list"]),
        )

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

    async def search_screen(  # pylint: disable=too-many-return-statements  # one return per searchable track
        self, query: str
    ) -> list[str]:
        """Re-render the current screen filtered by *query* for "/" search mode.

        The :class:`~.screens.legacy.LegacyScreen` adapter calls this for screens
        not yet extracted into ``repl/screens/``.

        Args:
            query: Raw filter text; an empty/blank query shows the full screen.

        Returns:
            The filtered screen lines for the current track.
        """
        track = self.ctx.current.track
        cleaned = query.strip() or None
        if track == "route":
            if cleaned is None:
                return await self.render_current()
            process = await lookup.current_process(self.ctx, self.env)
            if process is None:
                return ["Route not found."]
            return await self._search_route(process, cleaned)
        return await self.render_current()

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

    async def _render_stage_focus(self) -> list[str]:
        stage = await lookup.current_stage(self.ctx, self.env)
        if stage is None:
            return ["Stage not found."]
        sections = await gather_stage_sections(stage, self.env)
        navigator = self.rebuild_navigator([], stage_targets(sections))
        selected_id = navigator.selected.item_id if navigator.selected is not None else None
        return render_stage_screen(
            stage, sections, width=self.screen.width, selected_id=selected_id
        )

    async def _render_component_focus(self) -> list[str]:
        component = await lookup.current_component(self.ctx, self.env)
        if component is None:
            return ["Component not found."]
        material = await get_material_by_id(UUID(str(component.material_id)), self.env)
        sections = await gather_component_sections(component, material, self.env)
        display_name = await component_display_name(component, self.env)
        navigator = self.rebuild_navigator([], component_targets(sections))
        selected_id = navigator.selected.item_id if navigator.selected is not None else None
        return render_component_screen(
            sections,
            display_name=display_name,
            width=self.screen.width,
            selected_id=selected_id,
        )

    async def _render_risk_mode(  # pylint: disable=too-many-return-statements  # one return per risk scope
        self,
    ) -> list[str]:
        scope = self.ctx.current.risk_scope or "project"
        if scope == "project":
            project = await lookup.current_project(self.ctx, self.env)
            if project is None:
                return ["Project not found."]
            return await self._render_project_risks(project)
        if scope == "process":
            process = await lookup.current_process(self.ctx, self.env)
            if process is None:
                return ["Route not found."]
            return await self._render_process_risks(process)
        if scope == "stage":
            stage = await lookup.current_stage(self.ctx, self.env)
            if stage is None:
                return ["Stage not found."]
            return await self._render_stage_risks(stage)
        component = await lookup.current_component(self.ctx, self.env)
        if component is None:
            return ["Component not found."]
        return await self._render_component_risks(component)

    async def _render_project_risks(self, project: Project) -> list[str]:
        processes = await list_processes_for_project(UUID(str(project.id)), self.env)
        risks: list[dict[str, Any]] = []
        for process in processes:
            label = f"{process.route_number}.{process.process_number}"
            for risk in await list_risks_for_process(UUID(str(process.id)), self.env):
                risks.append(
                    {
                        "risk_type": risk.risk_type,
                        "name": risk.name,
                        "current_level": risk.current_level,
                        "mitigated_level": risk.mitigated_level,
                        "scope": label,
                    }
                )
        return await render_risk_table(
            risks, scope_label=f"project · {project.name}", width=self.screen.width
        )

    async def _render_process_risks(self, process: ManufacturingProcess) -> list[str]:
        risks = [
            {
                "risk_type": risk.risk_type,
                "name": risk.name,
                "current_level": risk.current_level,
                "mitigated_level": risk.mitigated_level,
                "scope": self.ctx.current.route_label or "process",
            }
            for risk in await list_risks_for_process(UUID(str(process.id)), self.env)
        ]
        return await render_risk_table(
            risks,
            scope_label=f"route {self.ctx.current.route_label or ''}",
            width=self.screen.width,
        )

    async def _render_stage_risks(self, stage: Stage) -> list[str]:
        risks = [
            {
                "risk_type": risk.risk_type,
                "name": risk.name,
                "current_level": risk.current_level,
                "mitigated_level": risk.mitigated_level,
                "scope": stage.name,
            }
            for risk in await list_risks_for_stage(UUID(str(stage.id)), self.env)
        ]
        return await render_risk_table(
            risks, scope_label=f"stage · {stage.name}", width=self.screen.width
        )

    async def _render_component_risks(self, component: Component) -> list[str]:
        risks = [
            {
                "risk_type": risk.risk_type,
                "name": risk.name,
                "current_level": risk.current_level,
                "mitigated_level": risk.mitigated_level,
                "scope": self.ctx.current.component_name or "component",
            }
            for risk in await list_risks_for_component(UUID(str(component.id)), self.env)
        ]
        return await render_risk_table(
            risks,
            scope_label=f"component · {self.ctx.current.component_name or ''}",
            width=self.screen.width,
        )

    async def _handle_route_list(self, process: ManufacturingProcess, kind: str) -> list[str]:
        if kind == "stages":
            stages = await list_stages_for_process(UUID(str(process.id)), self.env)
            if not stages:
                return ["Stages", "", "(none)"]
            return ["Stages", "", *[f"{stage.number}. {stage.name}" for stage in stages]]
        if kind == "components":
            return await self._list_components_for_process_lines(process)
        if kind == "risks":
            return await self._render_process_risks(process)
        if kind == "ncrm":
            return await self._list_process_ncrm_lines(process)
        return ["Usage: /list stages|components|risks|ncrm"]

    async def _handle_stage_list(self, stage: Stage, kind: str) -> list[str]:
        if kind == "risks":
            return await self._render_stage_risks(stage)
        if kind == "components":
            component_links = await list_stage_components(UUID(str(stage.id)), self.env)
            if not component_links:
                return ["Stage components", "", "(none)"]
            lines = ["Stage components", ""]
            for link in component_links:
                component = await get_component_by_id(UUID(str(link.component_id)), self.env)
                name = str(link.component_id)
                if component is not None:
                    name = await component_display_name(component, self.env)
                lines.append(f"{link.component_type}: {name}")
            return lines
        if kind == "ncrm":
            ncrm_links = await list_ncrms_for_stage(UUID(str(stage.id)), self.env)
            if not ncrm_links:
                return ["Stage NCRM", "", "(none)"]
            return [
                "Stage NCRM",
                "",
                *[f"{link.role.value}: {link.ncrm_id}" for link in ncrm_links],
            ]
        return ["Usage: /list risks|components|ncrm"]

    async def _handle_route_add(  # pylint: disable=too-many-return-statements  # one return per dispatch branch
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
                self.env,
            )
            if created is None:
                return await self.refresh_with_notice("Failed to create stage.", "error")
            return await self.refresh_with_notice(f"Created stage '{created.name}'.")
        if subject == "component" and len(args) >= 2:
            material_name = " ".join(args[1:])
            return self.modal.start_prompt(
                [
                    FieldSpec("control_strategy_role", required=False),
                    FieldSpec(
                        "is_isolated",
                        field_type="select",
                        options=BOOL_OPTIONS,
                        default="true",
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

    async def _start_route_risk_prompt(
        self,
        process: ManufacturingProcess,
        args: list[str],
    ) -> list[str]:
        if not args or args == ["process"]:
            return self.modal.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_process_risk_from_prompt(process, payload),
                title="Add risk",
            )
        if args[0].lower() == "stage" and len(args) >= 2:
            stage_name = " ".join(args[1:])
            stage = await lookup.find_stage(self.env, process, stage_name)
            if stage is None:
                return [f"Stage '{stage_name}' not found."]
            return self.modal.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                title="Add risk",
            )
        if args[0].lower() == "component" and len(args) >= 2:
            component_name = " ".join(args[1:])
            component = await lookup.find_component(self.env, process, component_name)
            if component is None:
                return [f"Component '{component_name}' not found."]
            return self.modal.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_component_risk_from_prompt(component, payload),
                title="Add risk",
            )
        return ["Usage: /add risk [stage <name>|component <name>|process]"]

    async def _handle_route_edit(self, process: ManufacturingProcess, args: list[str]) -> list[str]:
        if len(args) < 2:
            return ["Usage: /edit [stage <name>|component <name>]"]
        scope = args[0].lower()
        name = " ".join(args[1:])
        if scope == "stage":
            stage = await lookup.find_stage(self.env, process, name)
            if stage is None:
                return [f"Stage '{name}' not found."]
            return self.modal.start_prompt(
                [
                    FieldSpec("name", default=stage.name),
                    FieldSpec("number", field_type="int", default=str(stage.number)),
                ],
                lambda **payload: self._update_stage_from_prompt(stage, payload),
                title="Edit stage",
            )
        if scope == "component":
            component = await lookup.find_component(self.env, process, name)
            if component is None:
                return [f"Component '{name}' not found."]
            return self.modal.start_prompt(
                [
                    FieldSpec(
                        "control_strategy_role",
                        required=False,
                        default=component.control_strategy_role,
                    ),
                    FieldSpec(
                        "is_isolated",
                        field_type="select",
                        options=BOOL_OPTIONS,
                        default="true" if component.is_isolated else "false",
                    ),
                ],
                lambda **payload: self._update_component_from_prompt(component, payload),
                title="Edit component",
            )
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
            stage = await lookup.find_stage(self.env, process, name)
            if stage is None:
                return [f"Stage '{name}' not found."]
            return await self._delete_stage_with_confirmation(
                stage, ["--confirm"] if confirmed else []
            )
        if scope == "component":
            component = await lookup.find_component(self.env, process, name)
            if component is None:
                return [f"Component '{name}' not found."]
            return await self._delete_component_with_confirmation(
                component, ["--confirm"] if confirmed else []
            )
        return ["Usage: /delete [stage <name>|component <name>] --confirm"]

    async def _search_route(self, process: ManufacturingProcess, query: str) -> list[str]:
        lowered = query.lower()
        stage_matches = [
            stage
            for stage in await list_stages_for_process(UUID(str(process.id)), self.env)
            if lowered in stage.name.lower()
        ]
        component_lines = []
        for component in await list_components_for_process(UUID(str(process.id)), self.env):
            material = await get_material_by_id(UUID(str(component.material_id)), self.env)
            material_name = material.name if material else str(component.id)
            if lowered in material_name.lower():
                display = await component_display_name(component, self.env)
                component_lines.append(f"component: {display}")
        return [
            f"Search results for '{query}'",
            "",
            *[f"stage: {stage.name}" for stage in stage_matches],
            *component_lines,
        ] or [f"No matches for '{query}'."]

    async def _list_components_for_process_lines(self, process: ManufacturingProcess) -> list[str]:
        lines = ["Components", ""]
        components = await list_components_for_process(UUID(str(process.id)), self.env)
        if not components:
            return [*lines, "(none)"]
        for component in components:
            label = await component_display_name(component, self.env)
            role = component.control_strategy_role or "-"
            lines.append(f"{label} — {role}")
        return lines

    async def _list_process_ncrm_lines(self, process: ManufacturingProcess) -> list[str]:
        lines = ["NCRM links", ""]
        stages = await list_stages_for_process(UUID(str(process.id)), self.env)
        found = False
        for stage in stages:
            for link in await list_ncrms_for_stage(UUID(str(stage.id)), self.env):
                found = True
                lines.append(f"{stage.name}: {link.role.value} → {link.ncrm_id}")
        return lines if found else [*lines, "(none)"]

    async def open_project(self, project: Project) -> list[str]:
        """Push the project track for *project* and render its screen."""
        self.ctx.push(
            ContextFrame(track="project", project_id=str(project.id), project_name=project.name)
        )
        self.navigator = None
        self.session.push_project(str(project.id))
        self.session.update_context(
            track="project",
            project_id=str(project.id),
            process_id=None,
            stage_id=None,
            component_id=None,
        )
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

    async def _open_stage(self, stage: Stage) -> list[str]:
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
        return await self._render_stage_focus()

    async def _open_component(self, component: Component) -> list[str]:
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
        return await self._render_component_focus()

    async def _create_component_from_prompt(
        self,
        process: ManufacturingProcess,
        material_name: str,
        payload: dict[str, str | None],
    ) -> list[str]:
        material = await get_material_by_search(material_name, self.env)
        if material is None:
            return [f"Material '{material_name}' not found."]
        created = await create_component(
            ComponentCreate(
                process_id=UUID(str(process.id)),
                material_id=UUID(str(material.id)),
                control_strategy_role=payload.get("control_strategy_role"),
                is_isolated=as_bool(payload.get("is_isolated")),
            ),
            self.env,
        )
        if created is None:
            return await self.refresh_with_notice("Failed to create component.", "error")
        return await self.refresh_with_notice("Component created.")

    async def _start_stage_component_picker(
        self,
        stage: Stage,
        process: ManufacturingProcess,
    ) -> list[str]:
        """Open a picker of the process's components to assign one to *stage*.

        Components are created once at the route level; assigning one to a stage
        creates a :class:`StageComponent` link without creating a new component,
        so a single component can appear in several stages with different roles.
        """
        items = await self._process_component_items(process)
        if not items:
            return [
                "No components yet. Create one at the route level with /add component <material>.",
            ]
        return self.modal.start_picker(
            "Assign component to stage",
            items,
            lambda item: self._start_assign_role_prompt(stage, item),
        )

    async def _process_component_items(self, process: ManufacturingProcess) -> list[ListItem]:
        """Build picker items for every component in *process*, labelled by salt-form name.

        Each item's subtitle summarises the component's current stage assignments
        (``Stage {n} {role}``, comma-separated) so that several components sharing
        a material — e.g. a reactant reused across stages — stay distinguishable.
        Components with no assignments read ``unassigned``.

        Args:
            process: The manufacturing process whose components to list.

        Returns:
            One :class:`ListItem` per component (empty when the process has none).
        """
        components = await list_components_for_process(UUID(str(process.id)), self.env)
        assignments = await self._component_assignment_map(process)
        items: list[ListItem] = []
        for component in components:
            label = await component_display_name(component, self.env)
            if component.control_strategy_role:
                label = f"{label} ({component.control_strategy_role})"
            entries = sorted(assignments.get(str(component.id), []))
            subtitle = (
                ", ".join(f"Stage {number} {role}" for number, role in entries)
                if entries
                else "unassigned"
            )
            items.append(ListItem(label=label, subtitle=subtitle, item_id=str(component.id)))
        return items

    async def _component_assignment_map(
        self, process: ManufacturingProcess
    ) -> dict[str, list[tuple[int, str]]]:
        """Map each component id to its ``(stage_number, component_type)`` links."""
        assignments: dict[str, list[tuple[int, str]]] = {}
        for stage in await list_stages_for_process(UUID(str(process.id)), self.env):
            for link in await list_stage_components(UUID(str(stage.id)), self.env):
                assignments.setdefault(str(link.component_id), []).append(
                    (stage.number, link.component_type)
                )
        return assignments

    def _start_assign_role_prompt(self, stage: Stage, component_item: ListItem) -> list[str]:
        return self.modal.start_prompt(
            [
                FieldSpec(
                    "component_type",
                    field_type="select",
                    options=COMPONENT_TYPE_OPTIONS,
                ),
            ],
            lambda **payload: self._assign_component_to_stage(
                stage, component_item.item_id, payload
            ),
        )

    async def _assign_component_to_stage(
        self,
        stage: Stage,
        component_id: str,
        payload: dict[str, str | None],
    ) -> list[str]:
        link = await create_stage_component(
            StageComponentCreate(
                stage_id=UUID(str(stage.id)),
                component_id=UUID(component_id),
                component_type=payload.get("component_type") or "reactant",
            ),
            self.env,
        )
        if link is None:
            return await self.refresh_with_notice("Failed to assign component to stage.", "error")
        return await self.refresh_with_notice("Component assigned to stage.")

    async def _create_stage_risk_from_prompt(
        self,
        stage: Stage,
        payload: dict[str, str | None],
    ) -> list[str]:
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
            self.env,
        )
        if risk is None:
            return await self.refresh_with_notice("Failed to create stage risk.", "error")
        return await self.refresh_with_notice("Stage risk created.")

    async def _create_process_risk_from_prompt(
        self,
        process: ManufacturingProcess,
        payload: dict[str, str | None],
    ) -> list[str]:
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
            self.env,
        )
        if risk is None:
            return await self.refresh_with_notice("Failed to create process risk.", "error")
        return await self.refresh_with_notice("Process risk created.")

    async def _create_component_risk_from_prompt(
        self,
        component: Component,
        payload: dict[str, str | None],
    ) -> list[str]:
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
            self.env,
        )
        if risk is None:
            return await self.refresh_with_notice("Failed to create component risk.", "error")
        return await self.refresh_with_notice("Component risk created.")

    async def _start_stage_component_link_picker(self, process: ManufacturingProcess) -> list[str]:
        """Begin the stage → component → type typeahead chain for a link.

        Args:
            process: The manufacturing process owning the stages and components.
        """
        items = await self._stage_items(process)
        if not items:
            return ["Add a stage first with /add stage <name> --number N."]
        return self.modal.start_picker(
            "Select stage for component link",
            items,
            lambda item: self._start_stage_component_component_picker(process, item.item_id),
        )

    async def _start_stage_component_component_picker(
        self, process: ManufacturingProcess, stage_id: str
    ) -> list[str]:
        items = await self._process_component_items(process)
        if not items:
            return ["No components yet. Create one with /add component <material>."]
        return self.modal.start_picker(
            "Select component to link",
            items,
            lambda item: self._start_stage_component_type_prompt(stage_id, item.item_id),
        )

    def _start_stage_component_type_prompt(self, stage_id: str, component_id: str) -> list[str]:
        return self.modal.start_prompt(
            [FieldSpec("component_type", field_type="select", options=COMPONENT_TYPE_OPTIONS)],
            lambda **payload: self._create_stage_component_link(stage_id, component_id, payload),
        )

    async def _create_stage_component_link(
        self, stage_id: str, component_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        link = await create_stage_component(
            StageComponentCreate(
                stage_id=UUID(stage_id),
                component_id=UUID(component_id),
                component_type=payload.get("component_type") or "reactant",
            ),
            self.env,
        )
        return (
            ["Stage-component link created."]
            if link
            else ["Failed to create stage-component link."]
        )

    async def _start_stage_ncrm_link_picker(self, process: ManufacturingProcess) -> list[str]:
        """Begin the stage → NCRM → role typeahead chain for a link.

        Args:
            process: The manufacturing process owning the stages.
        """
        items = await self._stage_items(process)
        if not items:
            return ["Add a stage first with /add stage <name> --number N."]
        return self.modal.start_picker(
            "Select stage for NCRM link",
            items,
            lambda item: self._start_stage_ncrm_ncrm_picker(item.item_id),
        )

    async def _start_stage_ncrm_ncrm_picker(self, stage_id: str) -> list[str]:
        entries = await list_ncrm_library(self.env)
        if not entries:
            return ["Add an NCRM first via /library ncrm."]
        items = [ListItem(label=entry.display_name, item_id=str(entry.id)) for entry in entries]
        return self.modal.start_picker(
            "Assign NCRM to stage",
            items,
            lambda item: self._start_stage_ncrm_role_prompt(stage_id, item.item_id),
        )

    def _start_stage_ncrm_role_prompt(self, stage_id: str, ncrm_id: str) -> list[str]:
        return self.modal.start_prompt(
            [FieldSpec("role", field_type="select", options=enum_options(NcrmRole))],
            lambda **payload: self._create_stage_ncrm_link(stage_id, ncrm_id, payload),
        )

    async def _create_stage_ncrm_link(
        self, stage_id: str, ncrm_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        link = await create_stage_ncrm(
            StageNcrmCreate(
                stage_id=UUID(stage_id),
                ncrm_id=UUID(ncrm_id),
                role=NcrmRole(payload.get("role") or NcrmRole.REAGENT.value),
            ),
            self.env,
        )
        if link is None:
            return await self.refresh_with_notice("Failed to create stage-NCRM link.", "error")
        return await self.refresh_with_notice("Stage-NCRM link created.")

    async def _stage_items(self, process: ManufacturingProcess) -> list[ListItem]:
        """Build picker items for every stage in *process*, labelled by name.

        Args:
            process: The manufacturing process whose stages to list.

        Returns:
            One :class:`ListItem` per stage (empty when the process has none).
        """
        stages = await list_stages_for_process(UUID(str(process.id)), self.env)
        return [ListItem(label=stage.name, item_id=str(stage.id)) for stage in stages]

    async def _create_stage_ncrm_from_prompt(
        self,
        stage: Stage,
        ncrm_name: str,
        payload: dict[str, str | None],
    ) -> list[str]:
        ncrm = await get_ncrm_by_display_name(ncrm_name, self.env)
        if ncrm is None:
            return [f"NCRM '{ncrm_name}' not found."]
        link = await create_stage_ncrm(
            StageNcrmCreate(
                stage_id=UUID(str(stage.id)),
                ncrm_id=UUID(str(ncrm.id)),
                role=NcrmRole(payload.get("role") or NcrmRole.REAGENT.value),
            ),
            self.env,
        )
        if link is None:
            return await self.refresh_with_notice("Failed to create stage-NCRM link.", "error")
        return await self.refresh_with_notice("Stage-NCRM link created.")

    async def _update_process_from_prompt(
        self,
        process: ManufacturingProcess,
        payload: dict[str, str | None],
    ) -> list[str]:
        updated = await update_manufacturing_process(
            UUID(str(process.id)),
            ManufacturingProcessUpdate(
                route_number=optional_int(payload.get("route_number")),
                process_number=optional_int(payload.get("process_number")),
            ),
            self.env,
        )
        if updated is None:
            return await self.refresh_with_notice("Failed to update route.", "error")
        self.ctx.current.route_label = f"{updated.route_number}.{updated.process_number}"
        self.session.update_context(process_id=str(updated.id))
        return await self.refresh_with_notice(
            f"Updated route '{updated.route_number}.{updated.process_number}'."
        )

    async def _update_stage_from_prompt(
        self,
        stage: Stage,
        payload: dict[str, str | None],
    ) -> list[str]:
        updated = await update_stage(
            UUID(str(stage.id)),
            StageUpdate(
                name=payload.get("name") or None,
                number=optional_int(payload.get("number")),
            ),
            self.env,
        )
        if updated is None:
            return await self.refresh_with_notice("Failed to update stage.", "error")
        self.ctx.current.stage_name = updated.name
        self.session.update_context(stage_id=str(updated.id))
        return await self.refresh_with_notice(f"Updated stage '{updated.name}'.")

    async def _update_stage_ncrm_from_prompt(
        self,
        link_id: str,
        payload: dict[str, str | None],
    ) -> list[str]:
        updated = await update_stage_ncrm(
            UUID(link_id),
            StageNcrmUpdate(role=NcrmRole(payload.get("role") or NcrmRole.REAGENT.value)),
            self.env,
        )
        if updated is None:
            return await self.refresh_with_notice("Failed to update NCRM role.", "error")
        return await self.refresh_with_notice("NCRM role updated.")

    async def _update_stage_risk_from_prompt(
        self,
        risk_id: str,
        payload: dict[str, str | None],
    ) -> list[str]:
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
            self.env,
        )
        if updated is None:
            return await self.refresh_with_notice("Failed to update risk.", "error")
        return await self.refresh_with_notice(f"Updated risk '{updated.name}'.")

    async def _update_process_risk_from_prompt(
        self,
        risk_id: str,
        payload: dict[str, str | None],
    ) -> list[str]:
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
            self.env,
        )
        if updated is None:
            return await self.refresh_with_notice("Failed to update risk.", "error")
        return await self.refresh_with_notice(f"Updated risk '{updated.name}'.")

    async def _update_component_risk_from_prompt(
        self,
        risk_id: str,
        payload: dict[str, str | None],
    ) -> list[str]:
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
            self.env,
        )
        if updated is None:
            return await self.refresh_with_notice("Failed to update risk.", "error")
        return await self.refresh_with_notice(f"Updated risk '{updated.name}'.")

    async def _update_component_from_prompt(
        self,
        component: Component,
        payload: dict[str, str | None],
    ) -> list[str]:
        updated = await update_component(
            UUID(str(component.id)),
            ComponentUpdate(
                control_strategy_role=payload.get("control_strategy_role"),
                is_isolated=as_bool(payload.get("is_isolated")),
            ),
            self.env,
        )
        if updated is None:
            return await self.refresh_with_notice("Failed to update component.", "error")
        return await self.refresh_with_notice("Component updated.")

    async def _delete_stage_with_confirmation(self, stage: Stage, args: list[str]) -> list[str]:
        if "--confirm" not in args:
            return ["Re-run with --confirm to delete the stage."]
        success = await delete_stage(UUID(str(stage.id)), self.env)
        if not success:
            return await self.refresh_with_notice("Stage delete failed.", "error")
        self._pop_focus_to_parent()
        return await self.refresh_with_notice("Stage deleted.")

    async def _delete_component_with_confirmation(
        self, component: Component, args: list[str]
    ) -> list[str]:
        if "--confirm" not in args:
            return ["Re-run with --confirm to delete the component."]
        success = await delete_component(UUID(str(component.id)), self.env)
        if not success:
            return await self.refresh_with_notice("Component delete failed.", "error")
        self._pop_focus_to_parent()
        return await self.refresh_with_notice("Component deleted.")

    async def _start_stage_row_unassign(self, stage: Stage) -> list[str]:
        """Confirm-and-unassign the caret-selected component/NCRM/risk row.

        Unlike ``^X`` (which deletes the whole stage), this removes a single
        section row and keeps the user on the stage. Component rows carry the
        component id (for Enter-navigation), so the stage-component *link* id is
        resolved from the stage's links here.
        """
        navigator = self.list_navigator
        selected = navigator.selected if navigator is not None else None
        if selected is None:
            return await self.refresh_with_notice("Nothing selected.", "warning")
        kind, _, raw_id = selected.item_id.partition(":")
        if kind == "component":
            link_id = await self._stage_component_link_id(stage, raw_id)
            if link_id is None:
                return await self.refresh_with_notice("Component not found.", "error")
            return self.start_confirm(
                f"Unassign {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_stage_component(link_id, self.env), "Component unassigned."
                ),
            )
        if kind == "ncrm":
            return self.start_confirm(
                f"Unassign {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_stage_ncrm(UUID(raw_id), self.env), "NCRM unassigned."
                ),
            )
        if kind == "risk":
            return self.start_confirm(
                f"Delete risk '{selected.label}'",
                lambda: self._unassign_with_notice(
                    delete_stage_risk(UUID(raw_id), self.env), "Risk deleted."
                ),
            )
        return await self.refresh_with_notice("Nothing to unassign.", "warning")

    async def _start_component_row_unassign(self, component: Component) -> list[str]:
        """Confirm-and-delete the caret-selected salt or risk row.

        Mirrors :meth:`_start_stage_row_unassign` for the component-focus page;
        ``^X`` deletes the component itself, this removes a single row.
        """
        del component  # The selected row carries the id; component scopes the screen.
        navigator = self.list_navigator
        selected = navigator.selected if navigator is not None else None
        if selected is None:
            return await self.refresh_with_notice("Nothing selected.", "warning")
        kind, _, raw_id = selected.item_id.partition(":")
        if kind == "salt":
            return self.start_confirm(
                f"Unassign salt {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_component_salt(UUID(raw_id), self.env), "Salt unassigned."
                ),
            )
        if kind == "risk":
            return self.start_confirm(
                f"Delete risk '{selected.label}'",
                lambda: self._unassign_with_notice(
                    delete_component_risk(UUID(raw_id), self.env), "Risk deleted."
                ),
            )
        return await self.refresh_with_notice("Nothing to unassign.", "warning")

    async def _stage_component_link_id(self, stage: Stage, component_id: str) -> UUID | None:
        """Resolve the stage-component link id for a component row's component id."""
        links = await list_stage_components(UUID(str(stage.id)), self.env)
        for link in links:
            if str(link.component_id) == component_id:
                return UUID(str(link.id))
        return None

    async def _unassign_with_notice(self, delete_coro: Awaitable[bool], success: str) -> list[str]:
        """Await a delete operation, then refresh the screen with a status notice."""
        ok = await delete_coro
        if not ok:
            return await self.refresh_with_notice("Unassign failed.", "error")
        return await self.refresh_with_notice(success)

    def _pop_focus_to_parent(self) -> None:
        """Leave a focused stage/component screen after its entity was deleted.

        The current frame still references the now-deleted entity, so re-rendering
        it would fail; pop back to the parent (route) screen and re-sync session
        context before refreshing.
        """
        if self.ctx.current.track in {"stage_focus", "component_focus"}:
            self.ctx.pop()
            current = self.ctx.current
            self.session.update_context(
                track=current.track,
                project_id=current.project_id,
                process_id=current.process_id,
                stage_id=current.stage_id,
                component_id=current.component_id,
            )

    async def _start_salt_picker(self, component: Component) -> list[str]:
        counterions = await list_counterions(self.env)
        if not counterions:
            return ["Add a counterion first via /library counterions."]
        items = [
            ListItem(label=counterion.name, item_id=str(counterion.id))
            for counterion in counterions
        ]
        return self.modal.start_picker(
            "Select counterion for salt",
            items,
            lambda item: self._start_salt_details_prompt(component, item),
        )

    def _start_salt_details_prompt(self, component: Component, counterion: ListItem) -> list[str]:
        return self.modal.start_prompt(
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
        self,
        component: Component,
        counterion_id: str,
        payload: dict[str, str | None],
    ) -> list[str]:
        created = await create_component_salt(
            ComponentSaltCreate(
                component_id=UUID(str(component.id)),
                counterion_id=UUID(counterion_id),
                stoichiometry=optional_float(payload.get("stoichiometry")),
                is_fully_defined=optional_bool(payload.get("is_fully_defined")),
            ),
            self.env,
        )
        if created is None:
            return await self.refresh_with_notice("Failed to create salt record.", "error")
        return await self.refresh_with_notice("Created salt record.")

    def _risk_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("risk_type"),
            FieldSpec("name"),
            FieldSpec("description", required=False),
            FieldSpec("current_level", field_type="select", options=LEVEL_OPTIONS),
            FieldSpec("proposed_mitigation"),
            FieldSpec("mitigated_level", field_type="select", options=LEVEL_OPTIONS),
        ]

    def _risk_edit_fields(self, risk: Any) -> list[FieldSpec]:
        """Return the risk fields pre-filled from *risk* for an edit form.

        Stage, process, and component risks share the same editable columns, so
        one helper serves every scope. The level fields are number-selects on the
        1-5 severity scale, pre-selected to the risk's stored level.
        """
        return [
            FieldSpec("risk_type", default=risk.risk_type),
            FieldSpec("name", default=risk.name),
            FieldSpec("description", required=False, default=risk.description),
            FieldSpec(
                "current_level",
                field_type="select",
                options=LEVEL_OPTIONS,
                default=default_text(risk.current_level),
            ),
            FieldSpec("proposed_mitigation", default=risk.proposed_mitigation),
            FieldSpec(
                "mitigated_level",
                field_type="select",
                options=LEVEL_OPTIONS,
                default=default_text(risk.mitigated_level),
            ),
        ]

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
