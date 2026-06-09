"""Slash-command parsing and dispatch for the riskmanager CLI REPL."""
# pylint: disable=too-many-lines  # all 40+ command handlers live here intentionally; splitting would break cohesion

from __future__ import annotations

import csv
import inspect
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID

from ..config.settings import Environment
from ..model.enums import TA, NcrmRole
from ..model.tables import Component, ManufacturingProcess, Project, Stage
from ..operations.component_operations import (
    create_component,
    delete_component,
    get_component_by_id,
    list_components_for_process,
    update_component,
)
from ..operations.component_risks_operations import (
    create_component_risk,
    list_risks_for_component,
)
from ..operations.component_salt_operations import (
    create_component_salt,
    list_salts_for_component,
)
from ..operations.counterion_operations import (
    create_counterion,
    delete_counterion,
    list_counterions,
    update_counterion,
)
from ..operations.manufacturing_process_operations import (
    create_manufacturing_process,
    get_process_by_id,
    get_process_by_route,
    list_processes_for_project,
)
from ..operations.manufacturing_process_risk_operations import (
    create_manufacturing_process_risk,
    list_risks_for_process,
)
from ..operations.material_operations import (
    bulk_import_materials,
    create_material,
    delete_material,
    get_material_by_id,
    get_material_by_search,
    list_materials,
    update_material,
)
from ..operations.ncrm_library_operations import (
    create_ncrm_library_entry,
    delete_ncrm_library_entry,
    get_ncrm_by_display_name,
    list_ncrm_library,
    update_ncrm_library_entry,
)
from ..operations.project_operations import (
    create_project,
    get_project_by_id,
    list_projects,
    search_projects,
)
from ..operations.smiles_operations import canonicalize_smiles
from ..operations.stage_component_operations import (
    create_stage_component,
    list_stage_components,
)
from ..operations.stage_ncrm_operations import (
    create_stage_ncrm,
    list_ncrms_for_stage,
)
from ..operations.stage_operations import (
    create_stage,
    delete_stage,
    get_stage_by_name,
    list_stages_for_process,
    update_stage,
)
from ..operations.stage_risk_operations import create_stage_risk, list_risks_for_stage
from ..repl.renderers.admin_renderer import render_admin_screen
from ..repl.renderers.library_renderer import render_library_screen
from ..repl.renderers.project_renderer import render_project_screen
from ..repl.renderers.risk_renderer import render_risk_table
from ..repl.renderers.route_renderer import render_route_screen
from ..schema.create import (
    ComponentCreate,
    ComponentRiskCreate,
    ComponentSaltCreate,
    CounterionCreate,
    ManufacturingProcessCreate,
    ManufacturingProcessRiskCreate,
    MaterialCreate,
    NcrmLibraryCreate,
    ProjectCreate,
    StageComponentCreate,
    StageCreate,
    StageNcrmCreate,
    StageRiskCreate,
)
from ..schema.update import (
    ComponentUpdate,
    CounterionUpdate,
    MaterialUpdate,
    NcrmLibraryUpdate,
    StageUpdate,
)
from .context import ContextFrame, ContextManager
from .list_navigator import ListItem, ListNavigator
from .screen import ScreenManager
from .session_state import SessionState


@dataclass
class FieldSpec:
    """Specification for one guided-prompt field.

    Attributes:
        label: Human-readable field label.
        field_type: Validation kind: ``text``, ``int``, or ``choice``.
        required: Whether a value is mandatory.
        default: Optional default value.
        choices: Allowed values for ``choice`` fields.
    """

    label: str
    field_type: str = "text"
    required: bool = True
    default: str | None = None
    choices: list[str] = field(default_factory=list)


@dataclass
class PromptState:
    """Active guided prompt state."""

    fields: list[FieldSpec]
    collected: list[str | None]
    current_index: int = 0

    @property
    def current_field(self) -> FieldSpec:
        """Return the currently active field specification."""
        return self.fields[self.current_index]

    def submit_value(self, value: str) -> bool:
        """Submit a value for the active field.

        Args:
            value: Raw user-entered text.

        Returns:
            ``True`` when the prompt becomes complete.

        Raises:
            ValueError: If validation fails.
        """
        field_spec = self.current_field
        text = value.strip()
        normalized: str | None
        if not text:
            if field_spec.default is not None:
                normalized = field_spec.default
            elif field_spec.required:
                raise ValueError(f"{field_spec.label} is required.")
            else:
                normalized = None
        elif field_spec.field_type == "int":
            try:
                normalized = str(int(text))
            except ValueError as exc:
                raise ValueError(f"{field_spec.label} must be an integer.") from exc
        elif field_spec.field_type == "float":
            try:
                normalized = str(float(text))
            except ValueError as exc:
                raise ValueError(f"{field_spec.label} must be a number.") from exc
        elif field_spec.field_type == "choice":
            matches = [choice for choice in field_spec.choices if choice.lower() == text.lower()]
            if not matches:
                raise ValueError(
                    f"{field_spec.label} must be one of: {', '.join(field_spec.choices)}."
                )
            normalized = matches[0]
        else:
            normalized = text

        self.collected[self.current_index] = normalized
        self.current_index += 1
        return self.is_complete()

    def is_complete(self) -> bool:
        """Return ``True`` when all prompt fields have been collected."""
        return self.current_index >= len(self.fields)

    def as_dict(self) -> dict[str, str | None]:
        """Return collected values keyed by normalized field label."""
        return {
            _field_key(field_spec.label): self.collected[index]
            for index, field_spec in enumerate(self.fields)
        }


@dataclass
class PickerState:
    """Active typeahead-picker state.

    Why this exists: guided prompts collect a free-text line, but selecting a
    foreign-key target (a material for a project, a counterion for a salt) is
    far easier with a live, filterable list. The candidate set is loaded once
    and filtered in memory per keystroke, so no database call is made while the
    user types.

    Attributes:
        label: Prompt label shown while the picker is active.
        all_items: Full candidate list, filtered in memory per keystroke.
        on_select: Callback invoked with the highlighted item once chosen.
        query: Current filter text.
        navigator: Navigator over the current filtered matches.
    """

    label: str
    all_items: list[ListItem]
    on_select: Callable[[ListItem], Any]
    query: str = ""
    navigator: ListNavigator = field(init=False)

    def __post_init__(self) -> None:
        """Build the navigator over the unfiltered candidate list."""
        self.navigator = ListNavigator([], list(self.all_items))

    def set_query(self, query: str) -> None:
        """Filter candidates by case-insensitive substring match.

        Args:
            query: Raw filter text entered so far.
        """
        self.query = query
        lowered = query.strip().lower()
        matches = [item for item in self.all_items if lowered in item.label.lower()]
        self.navigator = ListNavigator([], matches)

    def move_up(self) -> None:
        """Move the highlight up through the current matches."""
        self.navigator.move_up()

    def move_down(self) -> None:
        """Move the highlight down through the current matches."""
        self.navigator.move_down()

    @property
    def selected(self) -> ListItem | None:
        """Return the highlighted match, if any."""
        return self.navigator.selected


class CommandDispatcher:  # pylint: disable=too-many-instance-attributes  # prompt, picker, and list-navigator modes each need their own state
    """Parse slash commands, update REPL state, and call operations."""

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
        self.ctx = ctx
        self.session = session
        self.screen = screen
        self.env = env
        self._prompt_state: PromptState | None = None
        self._prompt_callback: Callable[..., Any] | None = None
        self._list_navigator: ListNavigator | None = None
        self._picker_state: PickerState | None = None

    @property
    def prompt_state(self) -> PromptState | None:
        """Return the active guided prompt state, if any."""
        return self._prompt_state

    @property
    def list_navigator(self) -> ListNavigator | None:
        """Return the active list navigator, if any."""
        return self._list_navigator

    @property
    def picker_state(self) -> PickerState | None:
        """Return the active typeahead picker state, if any."""
        return self._picker_state

    def start_prompt(self, fields: list[FieldSpec], on_complete: Callable[..., Any]) -> list[str]:
        """Enter guided prompt mode.

        Args:
            fields: Prompt field definitions.
            on_complete: Callback invoked once all values are collected.

        Returns:
            Initial prompt-render lines.
        """
        self._prompt_state = PromptState(fields=fields, collected=[None] * len(fields))
        self._prompt_callback = on_complete
        return self._render_prompt_lines("Guided prompt started.")

    async def advance_prompt(self, value: str) -> list[str]:
        """Submit a value to the active guided prompt.

        Args:
            value: Raw user-entered value.

        Returns:
            Updated prompt lines or the completed callback result.
        """
        if self._prompt_state is None or self._prompt_callback is None:
            return ["No guided prompt is active."]
        try:
            is_complete = self._prompt_state.submit_value(value)
        except ValueError as exc:
            return self._render_prompt_lines(str(exc))
        if not is_complete:
            return self._render_prompt_lines()

        payload = self._prompt_state.as_dict()
        callback = self._prompt_callback
        self._prompt_state = None
        self._prompt_callback = None
        result = callback(**payload)
        if inspect.isawaitable(result):
            awaited = await result
            return self._coerce_lines(awaited)
        return self._coerce_lines(result)

    def cancel_prompt(self) -> list[str]:
        """Cancel the active guided prompt, if any."""
        self._prompt_state = None
        self._prompt_callback = None
        return ["Guided prompt cancelled."]

    def start_picker(
        self,
        label: str,
        all_items: list[ListItem],
        on_select: Callable[[ListItem], Any],
    ) -> list[str]:
        """Enter typeahead-picker mode.

        Args:
            label: Prompt label shown while the picker is active.
            all_items: Full candidate list to filter in memory.
            on_select: Callback invoked with the chosen item.

        Returns:
            Initial picker-render lines.
        """
        self._picker_state = PickerState(label=label, all_items=all_items, on_select=on_select)
        return self._render_picker_lines()

    def update_picker_query(self, query: str) -> list[str]:
        """Re-filter the active picker for *query* and re-render matches.

        Args:
            query: Raw filter text entered so far.

        Returns:
            Updated picker-render lines.
        """
        if self._picker_state is None:
            return ["No picker is active."]
        self._picker_state.set_query(query)
        return self._render_picker_lines()

    def picker_move(self, direction: str) -> list[str]:
        """Move the picker highlight up or down.

        Args:
            direction: Either ``"up"`` or ``"down"``.

        Returns:
            Updated picker-render lines.
        """
        if self._picker_state is None:
            return ["No picker is active."]
        if direction == "up":
            self._picker_state.move_up()
        else:
            self._picker_state.move_down()
        return self._render_picker_lines()

    async def picker_select(self) -> list[str]:
        """Choose the highlighted match and invoke the picker callback.

        Returns:
            The callback result, or a guidance line when nothing is selected.
        """
        if self._picker_state is None:
            return ["No picker is active."]
        selected = self._picker_state.selected
        if selected is None:
            return self._render_picker_lines()
        callback = self._picker_state.on_select
        self._picker_state = None
        result = callback(selected)
        if inspect.isawaitable(result):
            return self._coerce_lines(await result)
        return self._coerce_lines(result)

    def cancel_picker(self) -> list[str]:
        """Cancel the active typeahead picker, if any."""
        self._picker_state = None
        return ["Selection cancelled."]

    async def dispatch(  # pylint: disable=too-many-return-statements,too-many-branches  # top-level command router
        self, command: str
    ) -> list[str] | str:
        """Parse and execute a slash command.

        Args:
            command: Raw user-entered command string.

        Returns:
            Output lines, or the ``"__QUIT__"`` sentinel for REPL shutdown.
        """
        stripped = command.strip()
        if not stripped:
            return await self.render_current()
        if not stripped.startswith("/"):
            return [f"Unknown command: {stripped}. Type /help for commands."]

        try:
            parts = shlex.split(stripped)
        except ValueError as exc:
            return [f"Command parse error: {exc}"]
        if not parts:
            return ["Type /help for commands."]

        verb = parts[0].lower()
        args = parts[1:]
        global_result = await self._dispatch_global(verb, args)
        if global_result is not None:
            return global_result

        track = self.ctx.current.track
        if track == "home":
            return await self._dispatch_home(verb, args)
        if track == "project":
            return await self._dispatch_project(verb, args)
        if track == "route_select":
            return await self._dispatch_route_select(verb, args)
        if track == "route":
            return await self._dispatch_route(verb, args)
        if track == "stage_focus":
            return await self._dispatch_stage_focus(verb, args)
        if track == "component_focus":
            return await self._dispatch_component_focus(verb, args)
        if track == "library":
            return await self._dispatch_library(verb, args)
        if track == "admin":
            return await self._dispatch_admin(verb, args)
        if track == "risk_mode":
            return await self._dispatch_risk_mode(verb, args)
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def activate_list_selection(self, item: ListItem) -> list[str]:
        """Open the currently selected list item for list-driven screens.

        Args:
            item: Selected list item.

        Returns:
            Rendered lines for the activated screen.
        """
        if self.ctx.current.track == "home":
            project = await self._project_from_id(item.item_id)
            if project is None:
                return ["Project not found."]
            return await self._open_project(project)
        if self.ctx.current.track == "route_select":
            process = await self._process_from_id(item.item_id)
            project = await self._current_project()
            if process is None or project is None:
                return ["Route not found."]
            return await self._open_route(project, process)
        return await self.render_current()

    async def render_current(  # pylint: disable=too-many-return-statements  # one render path per navigation track
        self,
    ) -> list[str]:
        """Render the screen matching the current navigation context."""
        track = self.ctx.current.track
        if track == "home":
            return await self._render_home()
        if track == "project":
            project = await self._current_project()
            if project is None:
                return ["Project not found."]
            return await render_project_screen(project, self.env)
        if track == "route_select":
            return await self._render_route_select()
        if track == "route":
            process = await self._current_process()
            if process is None:
                return ["Route not found."]
            return await render_route_screen(process, self.env)
        if track == "stage_focus":
            return await self._render_stage_focus()
        if track == "component_focus":
            return await self._render_component_focus()
        if track == "library":
            return await self._render_library(self.ctx.current.library_sub or "select")
        if track == "admin":
            return render_admin_screen()
        if track == "risk_mode":
            return await self._render_risk_mode()
        return ["Home"]

    async def _dispatch_global(  # pylint: disable=too-many-return-statements  # one return per global command
        self, verb: str, args: list[str]
    ) -> list[str] | str | None:
        if verb == "/quit":
            return "__QUIT__"
        if verb == "/home":
            self.ctx.reset()
            self._list_navigator = None
            self.session.update_context(
                track="home",
                project_id=None,
                process_id=None,
                stage_id=None,
                component_id=None,
            )
            return await self._render_home()
        if verb == "/help":
            return self._help_lines(args[0] if args else None)
        if verb == "/library":
            sub_mode = args[0].lower() if args else "select"
            if sub_mode not in {"materials", "ncrm", "counterions", "select"}:
                return ["Usage: /library [materials|ncrm|counterions]"]
            self.ctx.push(ContextFrame(track="library", library_sub=sub_mode))
            self.session.update_context(track="library")
            return await self._render_library(sub_mode)
        if verb == "/admin" and not args:
            if self.ctx.current.track != "home":
                return ["/admin is only available from home."]
            self.ctx.push(ContextFrame(track="admin"))
            self.session.update_context(track="admin")
            return render_admin_screen()
        if verb == "/admin" and args:
            return await self._dispatch_admin(verb, args)
        return None

    async def _dispatch_home(self, verb: str, args: list[str]) -> list[str]:
        if verb == "/select" and args:
            query = " ".join(args)
            projects = await search_projects(query, self.env)
            if not projects:
                return [f"No project matched '{query}'."]
            return await self._open_project(projects[0])
        if verb == "/search" and args:
            return await self._render_home(" ".join(args))
        if verb == "/add" and args and args[0].lower() == "project":
            return self.start_prompt(
                [
                    FieldSpec("name"),
                    FieldSpec(
                        "therapy_area",
                        field_type="choice",
                        choices=[ta.value for ta in TA],
                    ),
                ],
                lambda **payload: self._start_project_material_picker(payload),
            )
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _dispatch_project(  # pylint: disable=too-many-return-statements  # one return per command verb
        self, verb: str, args: list[str]
    ) -> list[str]:
        project = await self._current_project()
        if project is None:
            return ["Project not found."]
        if verb == "/route":
            if not args:
                self.ctx.push(
                    ContextFrame(
                        track="route_select",
                        project_id=str(project.id),
                        project_name=project.name,
                    )
                )
                self.session.update_context(track="route_select", project_id=str(project.id))
                return await self._render_route_select()
            process = await self._process_from_route_label(str(project.id), args[0])
            if process is None:
                return [f"Route '{args[0]}' not found."]
            return await self._open_route(project, process)
        if verb == "/risks":
            self.ctx.push(
                ContextFrame(
                    track="risk_mode",
                    project_id=str(project.id),
                    project_name=project.name,
                    risk_scope="project",
                )
            )
            self.session.update_context(track="risk_mode", project_id=str(project.id))
            return await self._render_project_risks(project)
        if verb == "/add" and args and args[0].lower() == "process":
            return self.start_prompt(
                [
                    FieldSpec("route_number", field_type="int"),
                    FieldSpec("process_number", field_type="int"),
                ],
                lambda **payload: self._create_manufacturing_process_from_prompt(project, payload),
            )
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _dispatch_route_select(self, verb: str, args: list[str]) -> list[str]:
        if verb == "/search" and args:
            return await self._render_route_select(" ".join(args))
        if verb == "/route" and args:
            project = await self._current_project()
            if project is None:
                return ["Project not found."]
            process = await self._process_from_route_label(str(project.id), args[0])
            if process is None:
                return [f"Route '{args[0]}' not found."]
            return await self._open_route(project, process)
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _dispatch_route(  # pylint: disable=too-many-return-statements  # one return per command verb
        self, verb: str, args: list[str]
    ) -> list[str]:
        process = await self._current_process()
        project = await self._current_project()
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
                stage = await self._find_stage(process, target_name)
                if stage is None:
                    return [f"Stage '{target_name}' not found."]
                return await self._open_stage(stage)
            if scope == "component":
                component = await self._find_component(process, target_name)
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
        stage = await self._current_stage()
        process = await self._current_process()
        if stage is None or process is None:
            return ["Stage not found."]
        if verb == "/add" and args:
            if args[0].lower() == "risk":
                return self.start_prompt(
                    self._risk_fields(),
                    lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                )
            if args[0].lower() == "ncrm" and len(args) >= 2:
                ncrm_name = " ".join(args[1:])
                return self.start_prompt(
                    [
                        FieldSpec(
                            "role",
                            field_type="choice",
                            choices=[role.value for role in NcrmRole],
                        )
                    ],
                    lambda **payload: self._create_stage_ncrm_from_prompt(
                        stage,
                        ncrm_name,
                        payload,
                    ),
                )
            if args[0].lower() == "component" and len(args) >= 2:
                material_name = " ".join(args[1:])
                return self.start_prompt(
                    [
                        FieldSpec("control_strategy_role", required=False),
                        FieldSpec(
                            "is_isolated",
                            field_type="choice",
                            choices=["true", "false"],
                            default="false",
                        ),
                    ],
                    lambda **payload: self._create_component_for_stage(
                        stage,
                        process,
                        material_name,
                        payload,
                    ),
                )
        if verb == "/list" and args:
            return await self._handle_stage_list(stage, args[0].lower())
        if verb == "/edit":
            return self.start_prompt(
                [
                    FieldSpec("name", default=stage.name),
                    FieldSpec("number", field_type="int", default=str(stage.number)),
                ],
                lambda **payload: self._update_stage_from_prompt(stage, payload),
            )
        if verb == "/delete":
            return await self._delete_stage_with_confirmation(stage, args)
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _dispatch_component_focus(self, verb: str, args: list[str]) -> list[str]:
        component = await self._current_component()
        if component is None:
            return ["Component not found."]
        if verb == "/add" and args and args[0].lower() == "salt":
            return await self._start_salt_picker(component)
        if verb == "/edit":
            return self.start_prompt(
                [
                    FieldSpec(
                        "control_strategy_role",
                        required=False,
                        default=component.control_strategy_role,
                    ),
                    FieldSpec(
                        "is_isolated",
                        field_type="choice",
                        choices=["true", "false"],
                        default="true" if component.is_isolated else "false",
                    ),
                ],
                lambda **payload: self._update_component_from_prompt(component, payload),
            )
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

    async def _dispatch_library(  # pylint: disable=too-many-return-statements  # one return per command verb
        self, verb: str, args: list[str]
    ) -> list[str]:
        sub_mode = self.ctx.current.library_sub or "select"
        if verb == "/list":
            return await self._render_library(sub_mode)
        if verb == "/search" and args:
            return await self._render_library(sub_mode, query=" ".join(args))
        if verb == "/filter" and args:
            return await self._render_library(sub_mode, filter_mode=args[0].lower())
        if verb == "/show" and args:
            return await self._show_library_item(sub_mode, " ".join(args))
        if verb == "/add":
            return self._start_library_add_prompt(sub_mode)
        if verb == "/edit" and args:
            return await self._start_library_edit_prompt(sub_mode, " ".join(args))
        if verb == "/delete" and args:
            return await self._delete_library_item(sub_mode, " ".join(args))
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _dispatch_admin(self, verb: str, args: list[str]) -> list[str]:
        admin_args = args if verb == "/admin" else [verb.removeprefix("/admin"), *args]
        if not admin_args:
            return render_admin_screen()
        if admin_args[0] == "import" and len(admin_args) >= 3:
            return await self._admin_import(admin_args[1:])
        if admin_args[0] == "db" and len(admin_args) >= 2:
            return await self._admin_db(admin_args[1:])
        return ["Usage: /admin import <type> <file.csv> | /admin db <analyze|canonicalize>"]

    async def _dispatch_risk_mode(self, verb: str, args: list[str]) -> list[str]:
        if verb == "/list" and args and args[0].lower() == "risks":
            return await self._render_risk_mode()
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def _render_home(self, query: str | None = None) -> list[str]:
        projects = await list_projects(self.env)
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
        self._list_navigator = ListNavigator(recents, all_items)
        header = ["Projects", "", "Use arrows to navigate or /select <name>.", ""]
        return [*header, *self._list_navigator.render_lines(self.screen.width)]

    async def _render_route_select(self, query: str | None = None) -> list[str]:
        project = await self._current_project()
        if project is None:
            return ["Project not found."]
        processes = await list_processes_for_project(UUID(str(project.id)), self.env)
        if query:
            lowered = query.lower()
            processes = [
                process
                for process in processes
                if lowered in f"{process.route_number}.{process.process_number}".lower()
            ]
        recent_ids = self.session.recent_routes.get(str(project.id), [])
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
        self._list_navigator = ListNavigator(recents, all_items)
        return [
            f"Routes for {project.name}",
            "",
            "Use arrows to navigate or /route <R.P>.",
            "",
            *self._list_navigator.render_lines(self.screen.width),
        ]

    async def _render_stage_focus(self) -> list[str]:
        stage = await self._current_stage()
        if stage is None:
            return ["Stage not found."]
        risks = await list_risks_for_stage(UUID(str(stage.id)), self.env)
        links = await list_stage_components(UUID(str(stage.id)), self.env)
        ncrms = await list_ncrms_for_stage(UUID(str(stage.id)), self.env)
        return [
            f"Stage {stage.number}: {stage.name}",
            "",
            f"Risks: {len(risks)}",
            f"Components: {len(links)}",
            f"NCRM links: {len(ncrms)}",
        ]

    async def _render_component_focus(self) -> list[str]:
        component = await self._current_component()
        if component is None:
            return ["Component not found."]
        material = await get_material_by_id(UUID(str(component.material_id)), self.env)
        risks = await list_risks_for_component(UUID(str(component.id)), self.env)
        salts = await list_salts_for_component(UUID(str(component.id)), self.env)
        return [
            f"Component: {material.name if material else component.id}",
            "",
            f"Control role: {component.control_strategy_role or '-'}",
            f"Isolated: {'yes' if component.is_isolated else 'no'}",
            f"Risks: {len(risks)}",
            f"Salts: {len(salts)}",
        ]

    async def _render_library(
        self,
        sub_mode: str,
        query: str | None = None,
        filter_mode: str | None = None,
    ) -> list[str]:
        items = await self._library_items(sub_mode)
        if query:
            lowered = query.lower()
            items = [
                item
                for item in items
                if lowered in str(item.get("name") or item.get("display_name") or "").lower()
            ]
        if filter_mode == "has-smiles":
            items = [item for item in items if item.get("smiles")]
        if filter_mode == "no-smiles":
            items = [item for item in items if not item.get("smiles")]
        return await render_library_screen(sub_mode, items)

    async def _render_risk_mode(  # pylint: disable=too-many-return-statements  # one return per risk scope
        self,
    ) -> list[str]:
        scope = self.ctx.current.risk_scope or "project"
        if scope == "project":
            project = await self._current_project()
            if project is None:
                return ["Project not found."]
            return await self._render_project_risks(project)
        if scope == "process":
            process = await self._current_process()
            if process is None:
                return ["Route not found."]
            return await self._render_process_risks(process)
        if scope == "stage":
            stage = await self._current_stage()
            if stage is None:
                return ["Stage not found."]
            return await self._render_stage_risks(stage)
        component = await self._current_component()
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
        return await render_risk_table(risks, scope_label=f"project · {project.name}")

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
            risks, scope_label=f"route {self.ctx.current.route_label or ''}"
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
        return await render_risk_table(risks, scope_label=f"stage · {stage.name}")

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
            risks, scope_label=f"component · {self.ctx.current.component_name or ''}"
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
            return [
                "Stage components",
                "",
                *[f"{link.component_type}: {link.component_id}" for link in component_links],
            ]
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
            return [f"Created stage '{created.name}'."] if created else ["Failed to create stage."]
        if subject == "component" and len(args) >= 2:
            material_name = " ".join(args[1:])
            return self.start_prompt(
                [
                    FieldSpec("control_strategy_role", required=False),
                    FieldSpec(
                        "is_isolated",
                        field_type="choice",
                        choices=["true", "false"],
                        default="false",
                    ),
                ],
                lambda **payload: self._create_component_from_prompt(
                    process, material_name, payload
                ),
            )
        if subject == "risk":
            return await self._start_route_risk_prompt(process, args[1:])
        if subject == "stage-component":
            return self.start_prompt(
                [
                    FieldSpec("stage_name"),
                    FieldSpec("component_name"),
                    FieldSpec(
                        "component_type", field_type="choice", choices=["reactant", "product"]
                    ),
                ],
                lambda **payload: self._create_stage_component_from_prompt(process, payload),
            )
        if subject == "stage-ncrm":
            return self.start_prompt(
                [
                    FieldSpec("stage_name"),
                    FieldSpec("ncrm_name"),
                    FieldSpec(
                        "role", field_type="choice", choices=[role.value for role in NcrmRole]
                    ),
                ],
                lambda **payload: self._create_stage_ncrm_link_from_prompt(process, payload),
            )
        return ["Unsupported /add command."]

    async def _start_route_risk_prompt(
        self,
        process: ManufacturingProcess,
        args: list[str],
    ) -> list[str]:
        if not args or args == ["process"]:
            return self.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_process_risk_from_prompt(process, payload),
            )
        if args[0].lower() == "stage" and len(args) >= 2:
            stage_name = " ".join(args[1:])
            stage = await self._find_stage(process, stage_name)
            if stage is None:
                return [f"Stage '{stage_name}' not found."]
            return self.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
            )
        if args[0].lower() == "component" and len(args) >= 2:
            component_name = " ".join(args[1:])
            component = await self._find_component(process, component_name)
            if component is None:
                return [f"Component '{component_name}' not found."]
            return self.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_component_risk_from_prompt(component, payload),
            )
        return ["Usage: /add risk [stage <name>|component <name>|process]"]

    async def _handle_route_edit(self, process: ManufacturingProcess, args: list[str]) -> list[str]:
        if len(args) < 2:
            return ["Usage: /edit [stage <name>|component <name>]"]
        scope = args[0].lower()
        name = " ".join(args[1:])
        if scope == "stage":
            stage = await self._find_stage(process, name)
            if stage is None:
                return [f"Stage '{name}' not found."]
            return self.start_prompt(
                [
                    FieldSpec("name", default=stage.name),
                    FieldSpec("number", field_type="int", default=str(stage.number)),
                ],
                lambda **payload: self._update_stage_from_prompt(stage, payload),
            )
        if scope == "component":
            component = await self._find_component(process, name)
            if component is None:
                return [f"Component '{name}' not found."]
            return self.start_prompt(
                [
                    FieldSpec(
                        "control_strategy_role",
                        required=False,
                        default=component.control_strategy_role,
                    ),
                    FieldSpec(
                        "is_isolated",
                        field_type="choice",
                        choices=["true", "false"],
                        default="true" if component.is_isolated else "false",
                    ),
                ],
                lambda **payload: self._update_component_from_prompt(component, payload),
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
            stage = await self._find_stage(process, name)
            if stage is None:
                return [f"Stage '{name}' not found."]
            return await self._delete_stage_with_confirmation(
                stage, ["--confirm"] if confirmed else []
            )
        if scope == "component":
            component = await self._find_component(process, name)
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
                component_lines.append(f"component: {material_name}")
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
            material = await get_material_by_id(UUID(str(component.material_id)), self.env)
            mat_label = material.name if material else str(component.id)
            role = component.control_strategy_role or "-"
            lines.append(f"{mat_label} — {role}")
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

    async def _show_library_item(self, sub_mode: str, name: str) -> list[str]:
        items = await self._library_items(sub_mode)
        lowered = name.lower()
        for item in items:
            item_name = str(item.get("name") or item.get("display_name") or "")
            if item_name.lower() == lowered:
                return [f"{sub_mode} item", "", *[f"{key}: {value}" for key, value in item.items()]]
        return [f"No {sub_mode} item matched '{name}'."]

    def _start_library_add_prompt(self, sub_mode: str) -> list[str]:
        if sub_mode == "materials":
            return self.start_prompt(
                [FieldSpec("name"), FieldSpec("smiles", required=False)],
                lambda **payload: self._create_material_from_prompt(payload),
            )
        if sub_mode == "ncrm":
            return self.start_prompt(
                [
                    FieldSpec("display_name"),
                    FieldSpec("common_name"),
                    FieldSpec(
                        "interpret_chemically",
                        field_type="choice",
                        choices=["true", "false"],
                        default="false",
                    ),
                    FieldSpec("smiles", required=False),
                ],
                lambda **payload: self._create_ncrm_from_prompt(payload),
            )
        if sub_mode == "counterions":
            return self.start_prompt(
                [FieldSpec("name"), FieldSpec("smiles", required=False)],
                lambda **payload: self._create_counterion_from_prompt(payload),
            )
        return ["Choose a library subsection first."]

    async def _start_library_edit_prompt(self, sub_mode: str, name: str) -> list[str]:
        item = await self._find_library_item(sub_mode, name)
        if item is None:
            return [f"No {sub_mode} item matched '{name}'."]
        if sub_mode == "materials":
            return self.start_prompt(
                [
                    FieldSpec("name", default=str(item["name"])),
                    FieldSpec("smiles", required=False, default=_default_text(item.get("smiles"))),
                ],
                lambda **payload: self._update_material_entry(str(item["id"]), payload),
            )
        if sub_mode == "ncrm":
            return self.start_prompt(
                [
                    FieldSpec("display_name", default=str(item["display_name"])),
                    FieldSpec("common_name", default=str(item["common_name"])),
                    FieldSpec(
                        "interpret_chemically",
                        field_type="choice",
                        choices=["true", "false"],
                        default="true" if bool(item.get("interpret_chemically")) else "false",
                    ),
                    FieldSpec("smiles", required=False, default=_default_text(item.get("smiles"))),
                ],
                lambda **payload: self._update_ncrm_entry(str(item["id"]), payload),
            )
        return self.start_prompt(
            [
                FieldSpec("name", default=str(item["name"])),
                FieldSpec("smiles", required=False, default=_default_text(item.get("smiles"))),
            ],
            lambda **payload: self._update_counterion_entry(str(item["id"]), payload),
        )

    async def _delete_library_item(self, sub_mode: str, name: str) -> list[str]:
        item = await self._find_library_item(sub_mode, name)
        if item is None:
            return [f"No {sub_mode} item matched '{name}'."]
        item_uuid = UUID(str(item["id"]))
        if sub_mode == "materials":
            success = await delete_material(item_uuid, self.env)
        elif sub_mode == "ncrm":
            success = await delete_ncrm_library_entry(item_uuid, self.env)
        else:
            success = await delete_counterion(item_uuid, self.env)
        return ["Deleted."] if success else ["Delete failed."]

    async def _admin_import(self, args: list[str]) -> list[str]:
        import_type = args[0].lower()
        file_path = Path(args[1]).expanduser()
        dry_run = "--dry-run" in args[2:]
        skip_errors = "--skip-errors" in args[2:]
        if not file_path.exists():
            return [f"File not found: {file_path}"]
        content = file_path.read_text(encoding="utf-8")
        if import_type == "materials":
            counts = await bulk_import_materials(
                content,
                self.env,
                skip_errors=skip_errors,
                dry_run=dry_run,
            )
            created = counts["created"]
            skipped = counts["skipped"]
            errors = counts["errors"]
            return [f"materials import: created={created} skipped={skipped} errors={errors}"]
        return await self._admin_simple_import(
            import_type, content, dry_run=dry_run, skip_errors=skip_errors
        )

    async def _admin_simple_import(
        self,
        import_type: str,
        content: str,
        *,
        dry_run: bool,
        skip_errors: bool,
    ) -> list[str]:
        reader = csv.DictReader(StringIO(content))
        created = 0
        errors = 0
        for row in reader:
            try:
                operation_succeeded = False
                if import_type == "ncrm":
                    if dry_run:
                        created += 1
                        continue
                    ncrm_result = await create_ncrm_library_entry(
                        NcrmLibraryCreate(
                            display_name=(row.get("display_name") or "").strip(),
                            common_name=(row.get("common_name") or "").strip(),
                            interpret_chemically=(
                                (row.get("interpret_chemically") or "false").strip().lower()
                                == "true"
                            ),
                            smiles=(row.get("smiles") or "").strip() or None,
                        ),
                        self.env,
                    )
                    operation_succeeded = ncrm_result is not None
                elif import_type == "counterions":
                    if dry_run:
                        created += 1
                        continue
                    counterion_result = await create_counterion(
                        CounterionCreate(
                            name=(row.get("name") or "").strip(),
                            smiles=(row.get("smiles") or "").strip() or None,
                        ),
                        self.env,
                    )
                    operation_succeeded = counterion_result is not None
                else:
                    return ["Supported admin imports: materials, ncrm, counterions"]
                if not operation_succeeded:
                    errors += 1
                    if not skip_errors:
                        break
                else:
                    created += 1
            except Exception:  # pylint: disable=broad-exception-caught  # import loop must not abort on single-row error
                errors += 1
                if not skip_errors:
                    break
        return [f"{import_type} import: created={created} errors={errors} dry_run={dry_run}"]

    async def _admin_db(self, args: list[str]) -> list[str]:
        action = args[0].lower()
        ncrm_only = "--ncrm" in args[1:]
        dry_run = "--dry-run" in args[1:]
        if action == "analyze":
            return await self._admin_db_analyze(ncrm_only)
        if action == "canonicalize":
            return await self._admin_db_canonicalize(ncrm_only=ncrm_only, dry_run=dry_run)
        return ["Usage: /admin db analyze [--ncrm] | /admin db canonicalize [--dry-run] [--ncrm]"]

    async def _admin_db_analyze(self, ncrm_only: bool) -> list[str]:
        if ncrm_only:
            items = await list_ncrm_library(self.env)
            with_smiles = sum(1 for item in items if item.smiles)
            return [f"NCRM rows: {len(items)}", f"With SMILES: {with_smiles}"]
        materials = await list_materials(self.env)
        counterions = await list_counterions(self.env)
        ncrms = await list_ncrm_library(self.env)
        return [
            f"Materials: {len(materials)}",
            f"Counterions: {len(counterions)}",
            f"NCRM rows: {len(ncrms)}",
        ]

    async def _admin_db_canonicalize(self, *, ncrm_only: bool, dry_run: bool) -> list[str]:
        updated = 0
        if ncrm_only:
            items = await list_ncrm_library(self.env)
            for item in items:
                updated += await self._canonicalize_ncrm(item, dry_run)
            return [f"NCRM canonicalized: {updated}", f"Dry run: {dry_run}"]
        for material in await list_materials(self.env):
            if material.smiles:
                canonical = canonicalize_smiles(material.smiles)
                if canonical and canonical != material.smiles:
                    updated += 1
                    if not dry_run:
                        await update_material(
                            UUID(str(material.id)), MaterialUpdate(smiles=canonical), self.env
                        )
        for counterion in await list_counterions(self.env):
            if counterion.smiles:
                canonical = canonicalize_smiles(counterion.smiles)
                if canonical and canonical != counterion.smiles:
                    updated += 1
                    if not dry_run:
                        await update_counterion(
                            UUID(str(counterion.id)),
                            CounterionUpdate(smiles=canonical),
                            self.env,
                        )
        for item in await list_ncrm_library(self.env):
            updated += await self._canonicalize_ncrm(item, dry_run)
        return [f"Entries canonicalized: {updated}", f"Dry run: {dry_run}"]

    async def _canonicalize_ncrm(self, item: Any, dry_run: bool) -> int:
        if not item.smiles:
            return 0
        canonical = canonicalize_smiles(item.smiles)
        if not canonical or canonical == item.smiles:
            return 0
        if not dry_run:
            await update_ncrm_library_entry(
                UUID(str(item.id)),
                NcrmLibraryUpdate(smiles=canonical),
                self.env,
            )
        return 1

    async def _open_project(self, project: Project) -> list[str]:
        self.ctx.push(
            ContextFrame(track="project", project_id=str(project.id), project_name=project.name)
        )
        self._list_navigator = None
        self.session.push_project(str(project.id))
        self.session.update_context(
            track="project",
            project_id=str(project.id),
            process_id=None,
            stage_id=None,
            component_id=None,
        )
        return await render_project_screen(project, self.env)

    async def _open_route(self, project: Project, process: ManufacturingProcess) -> list[str]:
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
        self._list_navigator = None
        self.session.push_route(str(project.id), str(process.id))
        self.session.update_context(
            track="route",
            project_id=str(project.id),
            process_id=str(process.id),
            stage_id=None,
            component_id=None,
        )
        return await render_route_screen(process, self.env)

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
        material = await get_material_by_id(UUID(str(component.material_id)), self.env)
        self.ctx.push(
            ContextFrame(
                track="component_focus",
                project_id=self.ctx.current.project_id,
                project_name=self.ctx.current.project_name,
                process_id=self.ctx.current.process_id,
                route_label=self.ctx.current.route_label,
                component_id=str(component.id),
                component_name=material.name if material else str(component.id),
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
                is_isolated=_as_bool(payload.get("is_isolated")),
            ),
            self.env,
        )
        return ["Component created."] if created else ["Failed to create component."]

    async def _create_component_for_stage(
        self,
        stage: Stage,
        process: ManufacturingProcess,
        material_name: str,
        payload: dict[str, str | None],
    ) -> list[str]:
        material = await get_material_by_search(material_name, self.env)
        if material is None:
            return [f"Material '{material_name}' not found."]
        component = await create_component(
            ComponentCreate(
                process_id=UUID(str(process.id)),
                material_id=UUID(str(material.id)),
                control_strategy_role=payload.get("control_strategy_role"),
                is_isolated=_as_bool(payload.get("is_isolated")),
            ),
            self.env,
        )
        if component is None:
            return ["Failed to create component."]
        link = await create_stage_component(
            StageComponentCreate(
                stage_id=UUID(str(stage.id)),
                component_id=UUID(str(component.id)),
                component_type="reactant",
            ),
            self.env,
        )
        return ["Stage component created."] if link else ["Failed to link component to stage."]

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
                current_level=_optional_int(payload.get("current_level")),
                proposed_mitigation=payload.get("proposed_mitigation"),
                mitigated_level=_optional_int(payload.get("mitigated_level")),
            ),
            self.env,
        )
        return ["Stage risk created."] if risk else ["Failed to create stage risk."]

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
                current_level=_optional_int(payload.get("current_level")),
                proposed_mitigation=payload.get("proposed_mitigation"),
                mitigated_level=_optional_int(payload.get("mitigated_level")),
            ),
            self.env,
        )
        return ["Process risk created."] if risk else ["Failed to create process risk."]

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
                current_level=_optional_int(payload.get("current_level")),
                proposed_mitigation=payload.get("proposed_mitigation"),
                mitigated_level=_optional_int(payload.get("mitigated_level")),
            ),
            self.env,
        )
        return ["Component risk created."] if risk else ["Failed to create component risk."]

    async def _create_stage_component_from_prompt(
        self,
        process: ManufacturingProcess,
        payload: dict[str, str | None],
    ) -> list[str]:
        stage = await self._find_stage(process, payload.get("stage_name") or "")
        component = await self._find_component(process, payload.get("component_name") or "")
        if stage is None or component is None:
            return ["Stage or component not found."]
        link = await create_stage_component(
            StageComponentCreate(
                stage_id=UUID(str(stage.id)),
                component_id=UUID(str(component.id)),
                component_type=payload.get("component_type") or "reactant",
            ),
            self.env,
        )
        return (
            ["Stage-component link created."]
            if link
            else ["Failed to create stage-component link."]
        )

    async def _create_stage_ncrm_link_from_prompt(
        self,
        process: ManufacturingProcess,
        payload: dict[str, str | None],
    ) -> list[str]:
        stage = await self._find_stage(process, payload.get("stage_name") or "")
        ncrm = await get_ncrm_by_display_name(payload.get("ncrm_name") or "", self.env)
        if stage is None or ncrm is None:
            return ["Stage or NCRM not found."]
        link = await create_stage_ncrm(
            StageNcrmCreate(
                stage_id=UUID(str(stage.id)),
                ncrm_id=UUID(str(ncrm.id)),
                role=NcrmRole(payload.get("role") or NcrmRole.REAGENT.value),
            ),
            self.env,
        )
        return ["Stage-NCRM link created."] if link else ["Failed to create stage-NCRM link."]

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
        return ["Stage-NCRM link created."] if link else ["Failed to create stage-NCRM link."]

    async def _update_stage_from_prompt(
        self,
        stage: Stage,
        payload: dict[str, str | None],
    ) -> list[str]:
        updated = await update_stage(
            UUID(str(stage.id)),
            StageUpdate(
                name=payload.get("name") or None,
                number=_optional_int(payload.get("number")),
            ),
            self.env,
        )
        if updated is None:
            return ["Failed to update stage."]
        self.ctx.current.stage_name = updated.name
        self.session.update_context(stage_id=str(updated.id))
        return [f"Updated stage '{updated.name}'."]

    async def _update_component_from_prompt(
        self,
        component: Component,
        payload: dict[str, str | None],
    ) -> list[str]:
        updated = await update_component(
            UUID(str(component.id)),
            ComponentUpdate(
                control_strategy_role=payload.get("control_strategy_role"),
                is_isolated=_as_bool(payload.get("is_isolated")),
            ),
            self.env,
        )
        return ["Component updated."] if updated else ["Failed to update component."]

    async def _delete_stage_with_confirmation(self, stage: Stage, args: list[str]) -> list[str]:
        if "--confirm" not in args:
            return ["Re-run with --confirm to delete the stage."]
        success = await delete_stage(UUID(str(stage.id)), self.env)
        return ["Stage deleted."] if success else ["Stage delete failed."]

    async def _delete_component_with_confirmation(
        self, component: Component, args: list[str]
    ) -> list[str]:
        if "--confirm" not in args:
            return ["Re-run with --confirm to delete the component."]
        success = await delete_component(UUID(str(component.id)), self.env)
        return ["Component deleted."] if success else ["Component delete failed."]

    async def _create_material_from_prompt(self, payload: dict[str, str | None]) -> list[str]:
        created = await create_material(
            MaterialCreate(name=payload.get("name") or "", smiles=payload.get("smiles") or None),
            self.env,
        )
        return ["Material created."] if created else ["Failed to create material."]

    async def _create_ncrm_from_prompt(self, payload: dict[str, str | None]) -> list[str]:
        created = await create_ncrm_library_entry(
            NcrmLibraryCreate(
                display_name=payload.get("display_name") or "",
                common_name=payload.get("common_name") or "",
                interpret_chemically=_as_bool(payload.get("interpret_chemically")),
                smiles=payload.get("smiles") or None,
            ),
            self.env,
        )
        return ["NCRM entry created."] if created else ["Failed to create NCRM entry."]

    async def _create_counterion_from_prompt(self, payload: dict[str, str | None]) -> list[str]:
        created = await create_counterion(
            CounterionCreate(name=payload.get("name") or "", smiles=payload.get("smiles") or None),
            self.env,
        )
        return ["Counterion created."] if created else ["Failed to create counterion."]

    async def _start_project_material_picker(self, payload: dict[str, str | None]) -> list[str]:
        materials = await list_materials(self.env)
        if not materials:
            return ["Add a material first via /library materials."]
        items = [ListItem(label=material.name, item_id=str(material.id)) for material in materials]
        name = payload.get("name") or ""
        therapy_area = payload.get("therapy_area") or ""
        return self.start_picker(
            f"Select material for project '{name}'",
            items,
            lambda item: self._create_project_from_selection(name, therapy_area, item),
        )

    async def _create_project_from_selection(
        self,
        name: str,
        therapy_area: str,
        material: ListItem,
    ) -> list[str]:
        created = await create_project(
            ProjectCreate(
                name=name,
                therapy_area=TA(therapy_area),
                material_id=UUID(material.item_id),
            ),
            self.env,
        )
        if created is None:
            return ["Failed to create project."]
        return [f"Created project '{created.name}'.", "", *await self._render_home()]

    async def _create_manufacturing_process_from_prompt(
        self,
        project: Project,
        payload: dict[str, str | None],
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
            self.env,
        )
        if created is None:
            return ["Failed to create process."]
        return [
            f"Created process {created.route_number}.{created.process_number}.",
            "",
            *await render_project_screen(project, self.env),
        ]

    async def _start_salt_picker(self, component: Component) -> list[str]:
        counterions = await list_counterions(self.env)
        if not counterions:
            return ["Add a counterion first via /library counterions."]
        items = [
            ListItem(label=counterion.name, item_id=str(counterion.id))
            for counterion in counterions
        ]
        return self.start_picker(
            "Select counterion for salt",
            items,
            lambda item: self._start_salt_details_prompt(component, item),
        )

    def _start_salt_details_prompt(self, component: Component, counterion: ListItem) -> list[str]:
        return self.start_prompt(
            [
                FieldSpec("stoichiometry", field_type="float", required=False),
                FieldSpec(
                    "is_fully_defined",
                    field_type="choice",
                    choices=["true", "false"],
                    required=False,
                ),
            ],
            lambda **payload: self._create_component_salt_from_prompt(
                component, counterion.item_id, payload
            ),
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
                stoichiometry=_optional_float(payload.get("stoichiometry")),
                is_fully_defined=_optional_bool(payload.get("is_fully_defined")),
            ),
            self.env,
        )
        if created is None:
            return ["Failed to create salt record."]
        return ["Created salt record.", "", *await self._render_component_focus()]

    async def _update_material_entry(
        self, item_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        updated = await update_material(
            UUID(item_id),
            MaterialUpdate(name=payload.get("name"), smiles=payload.get("smiles") or None),
            self.env,
        )
        return ["Material updated."] if updated else ["Failed to update material."]

    async def _update_ncrm_entry(self, item_id: str, payload: dict[str, str | None]) -> list[str]:
        updated = await update_ncrm_library_entry(
            UUID(item_id),
            NcrmLibraryUpdate(
                display_name=payload.get("display_name"),
                common_name=payload.get("common_name"),
                interpret_chemically=_as_bool(payload.get("interpret_chemically")),
                smiles=payload.get("smiles") or None,
            ),
            self.env,
        )
        return ["NCRM updated."] if updated else ["Failed to update NCRM."]

    async def _update_counterion_entry(
        self, item_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        updated = await update_counterion(
            UUID(item_id),
            CounterionUpdate(name=payload.get("name"), smiles=payload.get("smiles") or None),
            self.env,
        )
        return ["Counterion updated."] if updated else ["Failed to update counterion."]

    async def _current_project(self) -> Project | None:
        project_id = self.ctx.current.project_id
        return await self._project_from_id(project_id)

    async def _current_process(self) -> ManufacturingProcess | None:
        process_id = self.ctx.current.process_id
        return await self._process_from_id(process_id)

    async def _current_stage(self) -> Stage | None:
        stage_id = self.ctx.current.stage_id
        if stage_id is None:
            return None
        process = await self._current_process()
        if process is None:
            return None
        for stage in await list_stages_for_process(UUID(str(process.id)), self.env):
            if str(stage.id) == stage_id:
                return stage
        return None

    async def _current_component(self) -> Component | None:
        component_id = self.ctx.current.component_id
        if component_id is None:
            return None
        return await get_component_by_id(UUID(component_id), self.env)

    async def _project_from_id(self, project_id: str | None) -> Project | None:
        if project_id is None:
            return None
        return await get_project_by_id(UUID(project_id), self.env)

    async def _process_from_id(self, process_id: str | None) -> ManufacturingProcess | None:
        if process_id is None:
            return None
        return await get_process_by_id(UUID(process_id), self.env)

    async def _process_from_route_label(
        self,
        project_id: str,
        route_label: str,
    ) -> ManufacturingProcess | None:
        try:
            route_number_text, process_number_text = route_label.split(".", maxsplit=1)
            return await get_process_by_route(
                UUID(project_id),
                int(route_number_text),
                int(process_number_text),
                self.env,
            )
        except ValueError:
            return None

    async def _find_stage(self, process: ManufacturingProcess, name: str) -> Stage | None:
        lowered = name.lower()
        exact = await get_stage_by_name(UUID(str(process.id)), name, self.env)
        if exact is not None:
            return exact
        for stage in await list_stages_for_process(UUID(str(process.id)), self.env):
            if lowered in stage.name.lower():
                return stage
        return None

    async def _find_component(self, process: ManufacturingProcess, name: str) -> Component | None:
        lowered = name.lower()
        for component in await list_components_for_process(UUID(str(process.id)), self.env):
            material = await get_material_by_id(UUID(str(component.material_id)), self.env)
            material_name = material.name if material else ""
            if (
                lowered in material_name.lower()
                or lowered in (component.control_strategy_role or "").lower()
            ):
                return component
        return None

    async def _library_items(self, sub_mode: str) -> list[dict[str, Any]]:
        if sub_mode == "materials":
            return [
                {"id": item.id, "name": item.name, "smiles": item.smiles}
                for item in await list_materials(self.env)
            ]
        if sub_mode == "ncrm":
            return [
                {
                    "id": item.id,
                    "display_name": item.display_name,
                    "common_name": item.common_name,
                    "interpret_chemically": item.interpret_chemically,
                    "smiles": item.smiles,
                }
                for item in await list_ncrm_library(self.env)
            ]
        if sub_mode == "counterions":
            return [
                {"id": item.id, "name": item.name, "smiles": item.smiles}
                for item in await list_counterions(self.env)
            ]
        return []

    async def _find_library_item(self, sub_mode: str, name: str) -> dict[str, Any] | None:
        lowered = name.lower()
        for item in await self._library_items(sub_mode):
            item_name = str(item.get("name") or item.get("display_name") or "")
            if item_name.lower() == lowered:
                return item
        return None

    async def _recent_project_items(self, projects: list[Project]) -> list[ListItem]:
        project_map = {str(project.id): project for project in projects}
        items: list[ListItem] = []
        for project_id in self.session.recent_projects:
            project = project_map.get(project_id)
            if project is not None:
                items.append(ListItem(label=project.name, subtitle="(recent)", item_id=project_id))
        return items

    def _render_prompt_lines(self, message: str | None = None) -> list[str]:
        if self._prompt_state is None:
            return [message] if message else []
        lines = ["Guided prompt", ""]
        if message:
            lines.append(message)
            lines.append("")
        for index, field_spec in enumerate(self._prompt_state.fields):
            value = self._prompt_state.collected[index]
            display = value if value is not None else "…"
            prefix = "→" if index == self._prompt_state.current_index else " "
            lines.append(f"{prefix} {field_spec.label}: {display}")
        if not self._prompt_state.is_complete():
            current = self._prompt_state.current_field
            lines.extend(["", f"Enter {current.label}:"])
        return lines

    def _render_picker_lines(self) -> list[str]:
        if self._picker_state is None:
            return []
        return [
            self._picker_state.label,
            "Type to filter · arrows to move · Enter to select · Esc to cancel",
            "",
            *self._picker_state.navigator.render_lines(self.screen.width),
        ]

    def _risk_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("risk_type"),
            FieldSpec("name"),
            FieldSpec("description", required=False),
            FieldSpec("current_level", field_type="int", required=False),
            FieldSpec("proposed_mitigation", required=False),
            FieldSpec("mitigated_level", field_type="int", required=False),
        ]

    def _help_lines(self, topic: str | None) -> list[str]:
        if topic is not None:
            return [
                f"Help for {topic}",
                "",
                *HELP_TOPICS.get(topic, ["No detailed help available."]),
            ]
        track = self.ctx.current.track
        return [
            f"Help · {track}",
            "",
            *HELP_TOPICS.get(track, ["/help", "/home", "/quit"]),
        ]

    @staticmethod
    def _coerce_lines(result: Any) -> list[str]:
        if isinstance(result, list) and all(isinstance(item, str) for item in result):
            return result
        if isinstance(result, str):
            return [result]
        return [str(result)]


HELP_TOPICS: dict[str, list[str]] = {
    "home": ["/select <name>", "/add project", "/library [submode]", "/admin", "/quit"],
    "project": ["/route [R.P]", "/add process", "/risks", "/home"],
    "route": [
        "/list stages|components|risks|ncrm",
        "/focus stage <name>",
        "/focus component <name>",
        "/add stage <name> --number N",
        "/add component <name>",
        "/add risk [stage <name>|component <name>|process]",
    ],
    "component_focus": ["/add salt", "/edit", "/delete", "/risks", "/home"],
    "library": ["/list", "/search <query>", "/add", "/edit <name>", "/delete <name>"],
    "admin": [
        "/admin import <type> <file.csv> [--dry-run] [--skip-errors]",
        "/admin db analyze [--ncrm]",
        "/admin db canonicalize [--dry-run] [--ncrm]",
    ],
}


def _field_key(label: str) -> str:
    return label.strip().lower().replace(" ", "_")


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _as_bool(value: str | None) -> bool:
    return (value or "false").strip().lower() in {"1", "true", "yes", "y"}


def _default_text(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)
