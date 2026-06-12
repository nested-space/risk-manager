"""Slash-command parsing and dispatch for the riskmanager CLI REPL."""
# pylint: disable=too-many-lines  # all 40+ command handlers live here intentionally; splitting would break cohesion

from __future__ import annotations

import csv
import inspect
import shlex
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID

from ..config.settings import Environment
from ..model.enums import TA, NcrmRole
from ..model.severity import LEVEL_OPTIONS
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
    delete_component_risk,
    list_risks_for_component,
    update_component_risk,
)
from ..operations.component_salt_operations import (
    create_component_salt,
    delete_component_salt,
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
    update_manufacturing_process,
)
from ..operations.manufacturing_process_risk_operations import (
    create_manufacturing_process_risk,
    list_risks_for_process,
    update_manufacturing_process_risk,
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
    update_project,
)
from ..operations.smiles_operations import canonicalize_smiles
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
    get_stage_by_name,
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
from ..repl.renderers.box import render_box
from ..repl.renderers.component_renderer import (
    component_targets,
    gather_component_sections,
    render_component_screen,
)
from ..repl.renderers.library_renderer import render_library_screen
from ..repl.renderers.project_renderer import render_project_screen
from ..repl.renderers.risk_renderer import render_risk_table
from ..repl.renderers.route_renderer import render_route_screen
from ..repl.renderers.stage_renderer import (
    gather_stage_sections,
    render_stage_screen,
    stage_targets,
)
from ..repl.renderers.tables import section_rule, section_width
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
    ComponentRiskUpdate,
    ComponentUpdate,
    CounterionUpdate,
    ManufacturingProcessRiskUpdate,
    ManufacturingProcessUpdate,
    MaterialUpdate,
    NcrmLibraryUpdate,
    ProjectUpdate,
    StageNcrmUpdate,
    StageRiskUpdate,
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
        field_type: Validation kind: ``text``, ``int``, ``float``, or ``select``.
        required: Whether a value is mandatory.
        default: Optional default value (a stored value for ``select`` fields).
        options: ``(label, value)`` pairs for ``select`` fields. The label is
            shown in the list while the value is what gets stored, so booleans
            can present ``Yes``/``No`` yet persist ``"true"``/``"false"``.
    """

    label: str
    field_type: str = "text"
    required: bool = True
    default: str | None = None
    options: list[tuple[str, str]] = field(default_factory=list)


#: Yes/No options for required boolean ``select`` fields.
BOOL_OPTIONS: list[tuple[str, str]] = [("Yes", "true"), ("No", "false")]

#: Yes/No options for optional boolean ``select`` fields, with an unset choice
#: that stores an empty string (coerced to ``None`` downstream).
OPTIONAL_BOOL_OPTIONS: list[tuple[str, str]] = [("Not specified", ""), *BOOL_OPTIONS]

#: Allowed component-type values for stage-component links.
COMPONENT_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("reactant", "reactant"),
    ("product", "product"),
]

#: No/Yes options for confirmation prompts, defaulting to the safe "No" choice.
CONFIRM_OPTIONS: list[tuple[str, str]] = [("No", "no"), ("Yes", "yes")]

# Control-character hotkeys (``str(key)`` for Ctrl-<letter> in the blessed loop).
# Terminal-reserved combos are avoided: Ctrl-C/D (interrupt/EOF, handled in the
# loop), Ctrl-S/Q (flow control), Ctrl-Z (suspend), Ctrl-H/I/J/M (backspace, tab,
# newline, carriage return), and Ctrl-[ (escape).
CTRL_A = "\x01"  # add
CTRL_B = "\x02"  # library
CTRL_E = "\x05"  # edit
CTRL_F = "\x06"  # focus / filter
CTRL_G = "\x07"  # go home
CTRL_L = "\x0c"  # list
CTRL_N = "\x0e"  # admin
CTRL_O = "\x0f"  # open / show
CTRL_R = "\x12"  # risks
CTRL_T = "\x14"  # routes
CTRL_U = "\x15"  # unassign
CTRL_X = "\x18"  # delete


def _enum_options(enum_cls: type[Enum]) -> list[tuple[str, str]]:
    """Return ``(label, value)`` select options for a string enum.

    Args:
        enum_cls: The enum to enumerate. Members must have string values.

    Returns:
        One ``(value, value)`` pair per member, in definition order.
    """
    return [(str(member.value), str(member.value)) for member in enum_cls]


def _match_select_value(field_spec: FieldSpec, text: str) -> str:
    """Resolve typed *text* to a select field's stored value.

    Matches case-insensitively against each option's value first, then its label,
    so both interactive selection and text-driven callers (e.g. tests) work.

    Args:
        field_spec: The active select field.
        text: Non-empty user-entered text.

    Returns:
        The stored value of the matched option.

    Raises:
        ValueError: If *text* matches no option.
    """
    lowered = text.lower()
    for _, value in field_spec.options:
        if value.lower() == lowered:
            return value
    for label, value in field_spec.options:
        if label.lower() == lowered:
            return value
    allowed = ", ".join(label for label, _ in field_spec.options)
    raise ValueError(f"{field_spec.label} must be one of: {allowed}.")


@dataclass
class PromptState:
    """Active guided prompt state."""

    fields: list[FieldSpec]
    collected: list[str | None]
    current_index: int = 0
    title: str | None = None
    _select_navigator: ListNavigator | None = field(default=None, init=False, repr=False)

    @property
    def current_field(self) -> FieldSpec:
        """Return the currently active field specification."""
        return self.fields[self.current_index]

    @property
    def is_select_field(self) -> bool:
        """Return ``True`` when the active field is a list selection."""
        return not self.is_complete() and self.current_field.field_type == "select"

    def select_navigator(self) -> ListNavigator | None:
        """Return the navigator for the active select field, building it lazily.

        Returns ``None`` when the active field is not a ``select`` field.
        """
        if not self.is_select_field:
            self._select_navigator = None
            return None
        if self._select_navigator is None:
            field_spec = self.current_field
            items = [ListItem(label=label, item_id=value) for label, value in field_spec.options]
            navigator = ListNavigator([], items)
            if field_spec.default is not None:
                navigator.select_item_id(field_spec.default)
            self._select_navigator = navigator
        return self._select_navigator

    def move_selection(self, direction: str) -> None:
        """Move the highlight of the active select field up or down.

        Args:
            direction: Either ``"up"`` or ``"down"``.
        """
        navigator = self.select_navigator()
        if navigator is None:
            return
        if direction == "up":
            navigator.move_up()
        else:
            navigator.move_down()

    def submit_selection(self) -> bool:
        """Store the highlighted option of the active select field and advance.

        Returns:
            ``True`` when the prompt becomes complete.

        Raises:
            ValueError: If the active field is not a select or nothing is highlighted.
        """
        navigator = self.select_navigator()
        if navigator is None:
            raise ValueError("The current field is not a selection.")
        selected = navigator.selected
        if selected is None:
            raise ValueError(f"{self.current_field.label} requires a selection.")
        self.collected[self.current_index] = selected.item_id
        self.current_index += 1
        self._select_navigator = None
        return self.is_complete()

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
        elif field_spec.field_type == "select":
            normalized = _match_select_value(field_spec, text)
        else:
            normalized = text

        self.collected[self.current_index] = normalized
        self.current_index += 1
        self._select_navigator = None
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


class CommandDispatcher:  # pylint: disable=too-many-instance-attributes,too-many-public-methods  # modal state + hotkey/search/dispatch entry points
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
        self._notice: tuple[str, str] | None = None

    @property
    def prompt_state(self) -> PromptState | None:
        """Return the active guided prompt state, if any."""
        return self._prompt_state

    def prompt_prefill(self) -> str:
        """Return the editable initial text for the active prompt field.

        Edit forms pass the entity's current value as each field's ``default``.
        For text and numeric fields the loop seeds its input buffer with this so
        the existing value is visible and editable; ``select`` fields pre-fill via
        their navigator instead, and pending/complete prompts contribute nothing.
        """
        state = self._prompt_state
        if state is None or state.is_complete() or state.is_select_field:
            return ""
        return state.current_field.default or ""

    @property
    def list_navigator(self) -> ListNavigator | None:
        """Return the active list navigator, if any."""
        return self._list_navigator

    @property
    def picker_state(self) -> PickerState | None:
        """Return the active typeahead picker state, if any."""
        return self._picker_state

    def start_prompt(
        self,
        fields: list[FieldSpec],
        on_complete: Callable[..., Any],
        *,
        title: str | None = None,
    ) -> list[str]:
        """Enter guided prompt mode.

        Args:
            fields: Prompt field definitions.
            on_complete: Callback invoked once all values are collected.
            title: Optional form heading shown above multi-field forms.

        Returns:
            Initial prompt-render lines.
        """
        self._prompt_state = PromptState(
            fields=fields, collected=[None] * len(fields), title=title
        )
        self._prompt_callback = on_complete
        return self._render_prompt_lines()

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
        return await self._complete_prompt(is_complete)

    def prompt_move(self, direction: str) -> list[str]:
        """Move the highlight of the active select field up or down.

        Args:
            direction: Either ``"up"`` or ``"down"``.

        Returns:
            Updated prompt-render lines.
        """
        if self._prompt_state is None:
            return ["No guided prompt is active."]
        self._prompt_state.move_selection(direction)
        return self._render_prompt_lines()

    async def submit_prompt_selection(self) -> list[str]:
        """Submit the highlighted option of the active select field.

        Returns:
            Updated prompt lines or the completed callback result.
        """
        if self._prompt_state is None or self._prompt_callback is None:
            return ["No guided prompt is active."]
        try:
            is_complete = self._prompt_state.submit_selection()
        except ValueError as exc:
            return self._render_prompt_lines(str(exc))
        return await self._complete_prompt(is_complete)

    async def _complete_prompt(self, is_complete: bool) -> list[str]:
        """Re-render the prompt, or run its callback once all fields are collected.

        Args:
            is_complete: Whether the active prompt has collected every field.

        Returns:
            Updated prompt lines or the completed callback result.
        """
        if self._prompt_state is None or self._prompt_callback is None:
            return ["No guided prompt is active."]
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

    async def cancel_prompt(self) -> list[str]:
        """Cancel the active guided prompt and restore the current screen."""
        self._prompt_state = None
        self._prompt_callback = None
        return await self._refresh_with_notice("Cancelled.", "warning")

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

    async def cancel_picker(self) -> list[str]:
        """Cancel the active typeahead picker and restore the current screen."""
        self._picker_state = None
        return await self._refresh_with_notice("Cancelled.", "warning")

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

    async def activate_list_selection(  # pylint: disable=too-many-return-statements  # one return per list-driven track
        self, item: ListItem
    ) -> list[str]:
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
        if self.ctx.current.track == "project":
            process = await self._process_from_id(item.item_id)
            project = await self._current_project()
            if process is None or project is None:
                return ["Route not found."]
            return await self._open_route(project, process)
        if self.ctx.current.track == "route_select":
            process = await self._process_from_id(item.item_id)
            project = await self._current_project()
            if process is None or project is None:
                return ["Route not found."]
            return await self._open_route(project, process)
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

    def take_notice(self) -> tuple[str, str] | None:
        """Return and clear the pending status notice, if any.

        Returns:
            A ``(message, level)`` pair where *level* is ``"success"``,
            ``"warning"``, or ``"error"``; ``None`` when no notice is pending.
        """
        notice, self._notice = self._notice, None
        return notice

    async def _refresh_with_notice(self, message: str, level: str = "success") -> list[str]:
        """Set a transient status notice and re-render the current screen.

        Args:
            message: Status text shown right-aligned on the input row.
            level: Notice severity controlling its colour.

        Returns:
            The refreshed screen lines for the current navigation track.
        """
        self._notice = (message, level)
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
            return await self._render_project(project)
        if track == "route_select":
            return await self._render_route_select()
        if track == "route":
            process = await self._current_process()
            if process is None:
                return ["Route not found."]
            return await render_route_screen(
                process, self.env, width=self.screen.width, dim=self.screen.dim
            )
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
                        field_type="select",
                        options=_enum_options(TA),
                    ),
                ],
                lambda **payload: self._start_project_material_picker(payload),
                title="Add project",
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
                title="Add process",
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
                return self.start_prompt(
                    self._risk_fields(),
                    lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                    title="Add risk",
                )
            if args[0].lower() == "ncrm" and len(args) >= 2:
                ncrm_name = " ".join(args[1:])
                return self.start_prompt(
                    [
                        FieldSpec(
                            "role",
                            field_type="select",
                            options=_enum_options(NcrmRole),
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
        component = await self._current_component()
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

    # ------------------------------------------------------------------ #
    # Hotkey dispatch
    #
    # Commands are driven by Ctrl-<letter> hotkeys instead of typed slash
    # commands. ``handle_hotkey`` is the keystroke entry point, mirroring the
    # ``_dispatch_<track>`` router structure: no-argument actions reuse the
    # existing ``_dispatch_*`` handlers, while argument-bearing actions open a
    # chooser/form/picker chain that ends in the same leaf handlers the slash
    # commands use. Slash commands remain available through the ``:`` command
    # line, so ``dispatch`` is untouched.
    # ------------------------------------------------------------------ #

    async def handle_hotkey(self, key_text: str) -> list[str] | str | None:
        """Route a control-character hotkey for the current track.

        Args:
            key_text: The raw keystroke (a control character).

        Returns:
            Rendered lines, the ``"__QUIT__"`` sentinel, or ``None`` when the
            key is not a hotkey on the current screen (so the loop ignores it).
        """
        track = self.ctx.current.track
        if key_text == CTRL_G and track != "home":
            return await self._dispatch_global("/home", [])
        handler = {
            "home": self._hotkey_home,
            "project": self._hotkey_project,
            "route_select": self._hotkey_route_select,
            "route": self._hotkey_route,
            "stage_focus": self._hotkey_stage_focus,
            "component_focus": self._hotkey_component_focus,
            "library": self._hotkey_library,
            "admin": self._hotkey_admin,
            "risk_mode": self._hotkey_risk_mode,
        }.get(track)
        if handler is None:
            return None
        return await handler(key_text)

    async def _hotkey_home(self, key: str) -> list[str] | str | None:
        if key == CTRL_A:
            return await self._dispatch_home("/add", ["project"])
        if key == CTRL_B:
            return self._start_library_chooser()
        if key == CTRL_N:
            return await self._dispatch_global("/admin", [])
        return None

    async def _hotkey_project(self, key: str) -> list[str] | None:
        if key == CTRL_T:
            return await self._dispatch_project("/route", [])
        if key == CTRL_R:
            return await self._dispatch_project("/risks", [])
        if key == CTRL_A:
            return await self._dispatch_project("/add", ["process"])
        if key == CTRL_E:
            project = await self._current_project()
            if project is None:
                return ["Project not found."]
            return self._start_project_edit_form(project)
        return None

    async def _hotkey_route_select(self, key: str) -> list[str] | None:
        del key  # Routes are opened by list navigation or "/" search only.
        return None

    async def _hotkey_route(  # pylint: disable=too-many-return-statements  # one return per route hotkey
        self, key: str
    ) -> list[str] | None:
        process = await self._current_process()
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
        stage = await self._current_stage()
        process = await self._current_process()
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
            return self._start_confirm(
                f"Delete stage '{stage.name}'",
                lambda: self._delete_stage_with_confirmation(stage, ["--confirm"]),
            )
        return None

    async def _hotkey_component_focus(  # pylint: disable=too-many-return-statements  # one return per component hotkey
        self, key: str
    ) -> list[str] | None:
        component = await self._current_component()
        if component is None:
            return ["Component not found."]
        if key == CTRL_A:
            return await self._start_salt_picker(component)
        if key == CTRL_E:
            return self._start_component_edit_form(component)
        if key == CTRL_U:
            return await self._start_component_row_unassign(component)
        if key == CTRL_X:
            return self._start_confirm(
                "Delete component",
                lambda: self._delete_component_with_confirmation(component, ["--confirm"]),
            )
        if key == CTRL_R:
            return await self._dispatch_component_focus("/risks", [])
        return None

    async def _hotkey_library(  # pylint: disable=too-many-return-statements  # one return per library hotkey
        self, key: str
    ) -> list[str] | None:
        sub_mode = self.ctx.current.library_sub or "select"
        if key == CTRL_A:
            return self._start_library_add_prompt(sub_mode)
        if key == CTRL_E:
            return await self._start_library_edit_picker(sub_mode)
        if key == CTRL_X:
            return await self._start_library_delete_picker(sub_mode)
        if key == CTRL_O:
            return await self._start_library_show_picker(sub_mode)
        if key == CTRL_F:
            return self._start_library_filter_chooser(sub_mode)
        if key == CTRL_L:
            return await self._render_library(sub_mode)
        return None

    async def _hotkey_admin(self, key: str) -> list[str] | None:
        if key == CTRL_A:
            return self._start_admin_action_chooser()
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
            process = await self._current_process()
            if process is None:
                return ["Route not found."]
            return self.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_process_risk_from_prompt(process, payload),
                title="Add risk",
            )
        if scope == "stage":
            stage = await self._current_stage()
            if stage is None:
                return ["Stage not found."]
            return self.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                title="Add risk",
            )
        if scope == "component":
            component = await self._current_component()
            if component is None:
                return ["Component not found."]
            return self.start_prompt(
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
            process = await self._current_process()
            if process is None:
                return ["Route not found."]
            process_risks = await list_risks_for_process(UUID(str(process.id)), self.env)
            return self._start_risk_edit_picker(
                process_risks, self._start_process_risk_edit_form
            )
        if scope == "stage":
            stage = await self._current_stage()
            if stage is None:
                return ["Stage not found."]
            stage_risks = await list_risks_for_stage(UUID(str(stage.id)), self.env)
            return self._start_risk_edit_picker(stage_risks, self._start_stage_risk_edit_form)
        if scope == "component":
            component = await self._current_component()
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
        return self.start_picker("Edit risk", items, lambda item: open_edit(item.item_id))

    # ------------------------------------------------------------------ #
    # Chooser, picker, and confirmation chains
    # ------------------------------------------------------------------ #

    def _start_confirm(self, label: str, on_yes: Callable[[], Any]) -> list[str]:
        """Open a No/Yes confirmation prompt that runs *on_yes* when confirmed.

        Args:
            label: Prompt label (e.g. ``"Delete stage 'Coupling'"``).
            on_yes: Zero-argument callable run on confirmation; may be async.

        Returns:
            Initial prompt-render lines.
        """
        return self.start_prompt(
            [FieldSpec(label, field_type="select", options=CONFIRM_OPTIONS, default="no")],
            lambda **payload: self._resolve_confirm(payload[_field_key(label)], on_yes),
        )

    async def _resolve_confirm(self, answer: str | None, on_yes: Callable[[], Any]) -> list[str]:
        if answer != "yes":
            return await self._refresh_with_notice("Cancelled.", "warning")
        result = on_yes()
        if inspect.isawaitable(result):
            return self._coerce_lines(await result)
        return self._coerce_lines(result)

    def _start_library_chooser(self) -> list[str]:
        return self.start_prompt(
            [
                FieldSpec(
                    "library",
                    field_type="select",
                    options=[
                        ("materials", "materials"),
                        ("ncrm", "ncrm"),
                        ("counterions", "counterions"),
                    ],
                )
            ],
            lambda **payload: self._dispatch_global("/library", [payload["library"]]),
        )

    def _start_route_add_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.start_prompt(
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
            return self.start_prompt(
                [FieldSpec("name"), FieldSpec("number", field_type="int")],
                lambda **payload: self._create_stage_from_prompt(process, payload),
                title="Add stage",
            )
        if kind == "component":
            return await self._start_component_add_picker(process)
        if kind == "risk":
            return self.start_prompt(
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
                number=_optional_int(payload.get("number")) or 0,
            ),
            self.env,
        )
        if created is None:
            return await self._refresh_with_notice("Failed to create stage.", "error")
        return await self._refresh_with_notice(f"Created stage '{created.name}'.")

    async def _start_component_add_picker(self, process: ManufacturingProcess) -> list[str]:
        materials = await list_materials(self.env)
        if not materials:
            return ["Add a material first via the library."]
        items = [ListItem(label=material.name, item_id=str(material.id)) for material in materials]
        return self.start_picker(
            "Select material for component",
            items,
            lambda item: self._start_component_details_prompt(process, item),
        )

    def _start_component_details_prompt(
        self, process: ManufacturingProcess, material_item: ListItem
    ) -> list[str]:
        return self.start_prompt(
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
                is_isolated=_as_bool(payload.get("is_isolated")),
            ),
            self.env,
        )
        if created is None:
            return await self._refresh_with_notice("Failed to create component.", "error")
        return await self._refresh_with_notice("Component created.")

    def _start_route_focus_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.start_prompt(
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
            return self.start_picker(
                "Focus stage",
                items,
                lambda item: self._open_stage_by_id(process, item.item_id),
            )
        items = await self._process_component_items(process)
        if not items:
            return ["No components yet."]
        return self.start_picker(
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

    def _start_project_edit_form(self, project: Project) -> list[str]:
        return self.start_prompt(
            [
                FieldSpec("name", default=project.name),
                FieldSpec(
                    "therapy_area",
                    field_type="select",
                    options=_enum_options(TA),
                    default=project.therapy_area.value,
                ),
            ],
            lambda **payload: self._update_project_from_prompt(project, payload),
            title="Edit project",
        )

    def _start_route_edit_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.start_prompt(
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
        return self.start_prompt(
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
            return self.start_picker(
                "Edit stage",
                items,
                lambda item: self._start_stage_edit_form_by_id(process, item.item_id),
            )
        items = await self._process_component_items(process)
        if not items:
            return ["No components yet."]
        return self.start_picker(
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
        return self.start_prompt(
            [
                FieldSpec("name", default=stage.name),
                FieldSpec("number", field_type="int", default=str(stage.number)),
            ],
            lambda **payload: self._update_stage_from_prompt(stage, payload),
            title="Edit stage",
        )

    async def _start_stage_ncrm_edit_form(self, link_id: str) -> list[str]:
        """Open a role-edit form for the stage-NCRM link with id *link_id*."""
        stage = await self._current_stage()
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
        return self.start_prompt(
            [
                FieldSpec(
                    "role",
                    field_type="select",
                    options=_enum_options(NcrmRole),
                    default=link.role.value,
                )
            ],
            lambda **payload: self._update_stage_ncrm_from_prompt(link_id, payload),
        )

    async def _start_stage_risk_edit_form(self, risk_id: str) -> list[str]:
        """Open an edit form for the stage risk with id *risk_id*."""
        stage = await self._current_stage()
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
        return self.start_prompt(
            self._risk_edit_fields(risk),
            lambda **payload: self._update_stage_risk_from_prompt(risk_id, payload),
            title="Edit risk",
        )

    async def _start_process_risk_edit_form(self, risk_id: str) -> list[str]:
        """Open an edit form for the process risk with id *risk_id*."""
        process = await self._current_process()
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
        return self.start_prompt(
            self._risk_edit_fields(risk),
            lambda **payload: self._update_process_risk_from_prompt(risk_id, payload),
            title="Edit risk",
        )

    async def _start_component_risk_edit_form(self, risk_id: str) -> list[str]:
        """Open an edit form for the component risk with id *risk_id*."""
        component = await self._current_component()
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
        return self.start_prompt(
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
        return self.start_prompt(
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
        return self.start_prompt(
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
            return self.start_picker(
                "Delete stage",
                items,
                lambda item: self._confirm_delete_stage_by_id(process, item.item_id),
            )
        items = await self._process_component_items(process)
        if not items:
            return ["No components yet."]
        return self.start_picker(
            "Delete component",
            items,
            lambda item: self._confirm_delete_component_by_id(item.item_id),
        )

    async def _confirm_delete_stage_by_id(
        self, process: ManufacturingProcess, stage_id: str
    ) -> list[str]:
        for stage in await list_stages_for_process(UUID(str(process.id)), self.env):
            if str(stage.id) == stage_id:
                return self._start_confirm(
                    f"Delete stage '{stage.name}'",
                    lambda: self._delete_stage_with_confirmation(stage, ["--confirm"]),
                )
        return ["Stage not found."]

    async def _confirm_delete_component_by_id(self, component_id: str) -> list[str]:
        component = await get_component_by_id(UUID(component_id), self.env)
        if component is None:
            return ["Component not found."]
        return self._start_confirm(
            "Delete component",
            lambda: self._delete_component_with_confirmation(component, ["--confirm"]),
        )

    def _start_route_list_chooser(self, process: ManufacturingProcess) -> list[str]:
        return self.start_prompt(
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
        return self.start_prompt(
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
            return self.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                title="Add risk",
            )
        if kind == "ncrm":
            return await self._start_stage_ncrm_ncrm_picker(str(stage.id))
        return await self._start_stage_component_picker(stage, process)

    def _start_stage_list_chooser(self, stage: Stage) -> list[str]:
        return self.start_prompt(
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

    async def _library_item_picker_items(self, sub_mode: str) -> list[ListItem]:
        names = [
            str(item.get("name") or item.get("display_name") or "")
            for item in await self._library_items(sub_mode)
        ]
        return [ListItem(label=name, item_id=name) for name in names if name]

    async def _start_library_edit_picker(self, sub_mode: str) -> list[str]:
        items = await self._library_item_picker_items(sub_mode)
        if not items:
            return [f"No {sub_mode} items to edit."]
        return self.start_picker(
            f"Edit {sub_mode} item",
            items,
            lambda item: self._start_library_edit_prompt(sub_mode, item.item_id),
        )

    async def _start_library_delete_picker(self, sub_mode: str) -> list[str]:
        items = await self._library_item_picker_items(sub_mode)
        if not items:
            return [f"No {sub_mode} items to delete."]
        return self.start_picker(
            f"Delete {sub_mode} item",
            items,
            lambda item: self._start_confirm(
                f"Delete '{item.item_id}'",
                lambda: self._delete_library_item(sub_mode, item.item_id),
            ),
        )

    async def _start_library_show_picker(self, sub_mode: str) -> list[str]:
        items = await self._library_item_picker_items(sub_mode)
        if not items:
            return [f"No {sub_mode} items to show."]
        return self.start_picker(
            f"Show {sub_mode} item",
            items,
            lambda item: self._show_library_item(sub_mode, item.item_id),
        )

    def _start_library_filter_chooser(self, sub_mode: str) -> list[str]:
        return self.start_prompt(
            [
                FieldSpec(
                    "filter",
                    field_type="select",
                    options=[
                        ("all", ""),
                        ("has SMILES", "has-smiles"),
                        ("no SMILES", "no-smiles"),
                    ],
                )
            ],
            lambda **payload: self._render_library(sub_mode, filter_mode=payload["filter"] or None),
        )

    def _start_admin_action_chooser(self) -> list[str]:
        return self.start_prompt(
            [
                FieldSpec(
                    "action",
                    field_type="select",
                    options=[
                        ("import CSV", "import"),
                        ("analyze database", "analyze"),
                        ("canonicalize SMILES", "canonicalize"),
                    ],
                )
            ],
            lambda **payload: self._admin_action_dispatch(payload["action"]),
        )

    async def _admin_action_dispatch(self, action: str) -> list[str]:
        if action == "import":
            return self.start_prompt(
                [
                    FieldSpec(
                        "type",
                        field_type="select",
                        options=[
                            ("materials", "materials"),
                            ("ncrm", "ncrm"),
                            ("counterions", "counterions"),
                        ],
                    ),
                    FieldSpec("file"),
                    FieldSpec(
                        "dry_run", field_type="select", options=BOOL_OPTIONS, default="false"
                    ),
                    FieldSpec(
                        "skip_errors", field_type="select", options=BOOL_OPTIONS, default="false"
                    ),
                ],
                lambda **payload: self._admin_import_from_prompt(payload),
                title="Import CSV",
            )
        scope_field = FieldSpec(
            "scope", field_type="select", options=[("all", "all"), ("ncrm only", "ncrm")]
        )
        if action == "analyze":
            return self.start_prompt(
                [scope_field],
                lambda **payload: self._admin_db(
                    ["analyze", *(["--ncrm"] if payload["scope"] == "ncrm" else [])]
                ),
            )
        return self.start_prompt(
            [
                scope_field,
                FieldSpec("dry_run", field_type="select", options=BOOL_OPTIONS, default="false"),
            ],
            lambda **payload: self._admin_db(
                [
                    "canonicalize",
                    *(["--ncrm"] if payload["scope"] == "ncrm" else []),
                    *(["--dry-run"] if _as_bool(payload["dry_run"]) else []),
                ]
            ),
        )

    async def _admin_import_from_prompt(self, payload: dict[str, str | None]) -> list[str]:
        args = [payload.get("type") or "", payload.get("file") or ""]
        if _as_bool(payload.get("dry_run")):
            args.append("--dry-run")
        if _as_bool(payload.get("skip_errors")):
            args.append("--skip-errors")
        return await self._admin_import(args)

    # ------------------------------------------------------------------ #
    # Search and help legend
    # ------------------------------------------------------------------ #

    def supports_search(self) -> bool:
        """Return ``True`` when the current track has an incremental "/" search."""
        return self.ctx.current.track in {"home", "route_select", "route", "library"}

    async def search(  # pylint: disable=too-many-return-statements  # one return per searchable track
        self, query: str
    ) -> list[str]:
        """Re-render the current screen filtered by *query* for "/" search mode.

        Args:
            query: Raw filter text; an empty/blank query shows the full screen.

        Returns:
            The filtered screen lines for the current track.
        """
        track = self.ctx.current.track
        cleaned = query.strip() or None
        if track == "home":
            return await self._render_home(cleaned)
        if track == "route_select":
            return await self._render_route_select(cleaned)
        if track == "library":
            sub_mode = self.ctx.current.library_sub or "select"
            return await self._render_library(sub_mode, query=cleaned)
        if track == "route":
            if cleaned is None:
                return await self.render_current()
            process = await self._current_process()
            if process is None:
                return ["Route not found."]
            return await self._search_route(process, cleaned)
        return await self.render_current()

    def help_legend(self) -> list[str]:
        """Return the hotkey legend lines for the current track."""
        track = self.ctx.current.track
        return [f"Hotkeys · {track}", "", *HELP_TOPICS.get(track, ["? help", "Ctrl-C back"])]

    def _rebuild_list_navigator(
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
        previous = self._list_navigator
        previous_id = (
            previous.selected.item_id
            if previous is not None and previous.selected is not None
            else None
        )
        navigator = ListNavigator(recents, all_items)
        if previous_id:
            navigator.select_item_id(previous_id)
        self._list_navigator = navigator
        return navigator

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
        navigator = self._rebuild_list_navigator(recents, all_items)
        header = [section_rule("Projects", section_width(self.screen.width)), ""]
        return [*header, *navigator.render_lines(self.screen.width)]

    async def _render_project(self, project: Project) -> list[str]:
        """Render the project screen with a navigable routes pick-list.

        The project's manufacturing processes are shown as a :class:`ListNavigator`
        so routes can be opened inline with the arrow keys and Enter, the same way
        projects are opened from the home screen.

        Args:
            project: The project whose screen to render.

        Returns:
            The composed project-screen lines, including the routes pick-list.
        """
        processes = await list_processes_for_project(UUID(str(project.id)), self.env)
        recent_ids = self.session.recent_routes.get(str(project.id), [])

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
        navigator = self._rebuild_list_navigator(recents, all_items)
        route_lines = navigator.render_lines(self.screen.width)
        return await render_project_screen(
            project, self.env, route_lines=route_lines, width=self.screen.width
        )

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
        navigator = self._rebuild_list_navigator(recents, all_items)
        return [
            f"Routes for {project.name}",
            "",
            "↑↓ navigate · Enter open · / search · ? help",
            "",
            *navigator.render_lines(self.screen.width),
        ]

    async def _render_stage_focus(self) -> list[str]:
        stage = await self._current_stage()
        if stage is None:
            return ["Stage not found."]
        sections = await gather_stage_sections(stage, self.env)
        navigator = self._rebuild_list_navigator([], stage_targets(sections))
        selected_id = navigator.selected.item_id if navigator.selected is not None else None
        return render_stage_screen(
            stage, sections, width=self.screen.width, selected_id=selected_id
        )

    async def _render_component_focus(self) -> list[str]:
        component = await self._current_component()
        if component is None:
            return ["Component not found."]
        material = await get_material_by_id(UUID(str(component.material_id)), self.env)
        sections = await gather_component_sections(component, material, self.env)
        navigator = self._rebuild_list_navigator([], component_targets(sections))
        selected_id = navigator.selected.item_id if navigator.selected is not None else None
        return render_component_screen(
            component, material, sections, width=self.screen.width, selected_id=selected_id
        )

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
            lines = ["Stage components", ""]
            for link in component_links:
                component = await get_component_by_id(UUID(str(link.component_id)), self.env)
                name = str(link.component_id)
                if component is not None:
                    material = await get_material_by_id(UUID(str(component.material_id)), self.env)
                    if material is not None:
                        name = material.name
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
                return await self._refresh_with_notice("Failed to create stage.", "error")
            return await self._refresh_with_notice(f"Created stage '{created.name}'.")
        if subject == "component" and len(args) >= 2:
            material_name = " ".join(args[1:])
            return self.start_prompt(
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
            return self.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_process_risk_from_prompt(process, payload),
                title="Add risk",
            )
        if args[0].lower() == "stage" and len(args) >= 2:
            stage_name = " ".join(args[1:])
            stage = await self._find_stage(process, stage_name)
            if stage is None:
                return [f"Stage '{stage_name}' not found."]
            return self.start_prompt(
                self._risk_fields(),
                lambda **payload: self._create_stage_risk_from_prompt(stage, payload),
                title="Add risk",
            )
        if args[0].lower() == "component" and len(args) >= 2:
            component_name = " ".join(args[1:])
            component = await self._find_component(process, component_name)
            if component is None:
                return [f"Component '{component_name}' not found."]
            return self.start_prompt(
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
            stage = await self._find_stage(process, name)
            if stage is None:
                return [f"Stage '{name}' not found."]
            return self.start_prompt(
                [
                    FieldSpec("name", default=stage.name),
                    FieldSpec("number", field_type="int", default=str(stage.number)),
                ],
                lambda **payload: self._update_stage_from_prompt(stage, payload),
                title="Edit stage",
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
                title="Add material",
            )
        if sub_mode == "ncrm":
            return self.start_prompt(
                [
                    FieldSpec("display_name"),
                    FieldSpec("common_name"),
                    FieldSpec(
                        "interpret_chemically",
                        field_type="select",
                        options=BOOL_OPTIONS,
                        default="false",
                    ),
                    FieldSpec("smiles", required=False),
                ],
                lambda **payload: self._create_ncrm_from_prompt(payload),
                title="Add NCRM",
            )
        if sub_mode == "counterions":
            return self.start_prompt(
                [FieldSpec("name"), FieldSpec("smiles", required=False)],
                lambda **payload: self._create_counterion_from_prompt(payload),
                title="Add counterion",
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
                title="Edit material",
            )
        if sub_mode == "ncrm":
            return self.start_prompt(
                [
                    FieldSpec("display_name", default=str(item["display_name"])),
                    FieldSpec("common_name", default=str(item["common_name"])),
                    FieldSpec(
                        "interpret_chemically",
                        field_type="select",
                        options=BOOL_OPTIONS,
                        default="true" if bool(item.get("interpret_chemically")) else "false",
                    ),
                    FieldSpec("smiles", required=False, default=_default_text(item.get("smiles"))),
                ],
                lambda **payload: self._update_ncrm_entry(str(item["id"]), payload),
                title="Edit NCRM",
            )
        return self.start_prompt(
            [
                FieldSpec("name", default=str(item["name"])),
                FieldSpec("smiles", required=False, default=_default_text(item.get("smiles"))),
            ],
            lambda **payload: self._update_counterion_entry(str(item["id"]), payload),
            title="Edit counterion",
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
        if not success:
            return await self._refresh_with_notice("Delete failed.", "error")
        return await self._refresh_with_notice("Deleted.")

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
        return await self._render_project(project)

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
        return await render_route_screen(
            process, self.env, width=self.screen.width, dim=self.screen.dim
        )

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
        if created is None:
            return await self._refresh_with_notice("Failed to create component.", "error")
        return await self._refresh_with_notice("Component created.")

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
        return self.start_picker(
            "Assign component to stage",
            items,
            lambda item: self._start_assign_role_prompt(stage, item),
        )

    async def _process_component_items(self, process: ManufacturingProcess) -> list[ListItem]:
        """Build picker items for every component in *process*, labelled by material.

        Args:
            process: The manufacturing process whose components to list.

        Returns:
            One :class:`ListItem` per component (empty when the process has none).
        """
        components = await list_components_for_process(UUID(str(process.id)), self.env)
        items: list[ListItem] = []
        for component in components:
            material = await get_material_by_id(UUID(str(component.material_id)), self.env)
            material_name = material.name if material else str(component.id)
            label = material_name
            if component.control_strategy_role:
                label = f"{material_name} ({component.control_strategy_role})"
            items.append(ListItem(label=label, item_id=str(component.id)))
        return items

    def _start_assign_role_prompt(self, stage: Stage, component_item: ListItem) -> list[str]:
        return self.start_prompt(
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
            return await self._refresh_with_notice("Failed to assign component to stage.", "error")
        return await self._refresh_with_notice("Component assigned to stage.")

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
        if risk is None:
            return await self._refresh_with_notice("Failed to create stage risk.", "error")
        return await self._refresh_with_notice("Stage risk created.")

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
        if risk is None:
            return await self._refresh_with_notice("Failed to create process risk.", "error")
        return await self._refresh_with_notice("Process risk created.")

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
        if risk is None:
            return await self._refresh_with_notice("Failed to create component risk.", "error")
        return await self._refresh_with_notice("Component risk created.")

    async def _start_stage_component_link_picker(
        self, process: ManufacturingProcess
    ) -> list[str]:
        """Begin the stage → component → type typeahead chain for a link.

        Args:
            process: The manufacturing process owning the stages and components.
        """
        items = await self._stage_items(process)
        if not items:
            return ["Add a stage first with /add stage <name> --number N."]
        return self.start_picker(
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
        return self.start_picker(
            "Select component to link",
            items,
            lambda item: self._start_stage_component_type_prompt(stage_id, item.item_id),
        )

    def _start_stage_component_type_prompt(self, stage_id: str, component_id: str) -> list[str]:
        return self.start_prompt(
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
        return self.start_picker(
            "Select stage for NCRM link",
            items,
            lambda item: self._start_stage_ncrm_ncrm_picker(item.item_id),
        )

    async def _start_stage_ncrm_ncrm_picker(self, stage_id: str) -> list[str]:
        entries = await list_ncrm_library(self.env)
        if not entries:
            return ["Add an NCRM first via /library ncrm."]
        items = [
            ListItem(label=entry.display_name, item_id=str(entry.id)) for entry in entries
        ]
        return self.start_picker(
            "Assign NCRM to stage",
            items,
            lambda item: self._start_stage_ncrm_role_prompt(stage_id, item.item_id),
        )

    def _start_stage_ncrm_role_prompt(self, stage_id: str, ncrm_id: str) -> list[str]:
        return self.start_prompt(
            [FieldSpec("role", field_type="select", options=_enum_options(NcrmRole))],
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
            return await self._refresh_with_notice("Failed to create stage-NCRM link.", "error")
        return await self._refresh_with_notice("Stage-NCRM link created.")

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
            return await self._refresh_with_notice("Failed to create stage-NCRM link.", "error")
        return await self._refresh_with_notice("Stage-NCRM link created.")

    async def _update_project_from_prompt(
        self,
        project: Project,
        payload: dict[str, str | None],
    ) -> list[str]:
        therapy_area = payload.get("therapy_area")
        updated = await update_project(
            UUID(str(project.id)),
            ProjectUpdate(
                name=payload.get("name") or None,
                therapy_area=TA(therapy_area) if therapy_area else None,
            ),
            self.env,
        )
        if updated is None:
            return await self._refresh_with_notice("Failed to update project.", "error")
        self.ctx.current.project_name = updated.name
        self.session.update_context(project_id=str(updated.id))
        return await self._refresh_with_notice(f"Updated project '{updated.name}'.")

    async def _update_process_from_prompt(
        self,
        process: ManufacturingProcess,
        payload: dict[str, str | None],
    ) -> list[str]:
        updated = await update_manufacturing_process(
            UUID(str(process.id)),
            ManufacturingProcessUpdate(
                route_number=_optional_int(payload.get("route_number")),
                process_number=_optional_int(payload.get("process_number")),
            ),
            self.env,
        )
        if updated is None:
            return await self._refresh_with_notice("Failed to update route.", "error")
        self.ctx.current.route_label = f"{updated.route_number}.{updated.process_number}"
        self.session.update_context(process_id=str(updated.id))
        return await self._refresh_with_notice(
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
                number=_optional_int(payload.get("number")),
            ),
            self.env,
        )
        if updated is None:
            return await self._refresh_with_notice("Failed to update stage.", "error")
        self.ctx.current.stage_name = updated.name
        self.session.update_context(stage_id=str(updated.id))
        return await self._refresh_with_notice(f"Updated stage '{updated.name}'.")

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
            return await self._refresh_with_notice("Failed to update NCRM role.", "error")
        return await self._refresh_with_notice("NCRM role updated.")

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
                current_level=_optional_int(payload.get("current_level")),
                proposed_mitigation=payload.get("proposed_mitigation"),
                mitigated_level=_optional_int(payload.get("mitigated_level")),
            ),
            self.env,
        )
        if updated is None:
            return await self._refresh_with_notice("Failed to update risk.", "error")
        return await self._refresh_with_notice(f"Updated risk '{updated.name}'.")

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
                current_level=_optional_int(payload.get("current_level")),
                proposed_mitigation=payload.get("proposed_mitigation"),
                mitigated_level=_optional_int(payload.get("mitigated_level")),
            ),
            self.env,
        )
        if updated is None:
            return await self._refresh_with_notice("Failed to update risk.", "error")
        return await self._refresh_with_notice(f"Updated risk '{updated.name}'.")

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
                current_level=_optional_int(payload.get("current_level")),
                proposed_mitigation=payload.get("proposed_mitigation"),
                mitigated_level=_optional_int(payload.get("mitigated_level")),
            ),
            self.env,
        )
        if updated is None:
            return await self._refresh_with_notice("Failed to update risk.", "error")
        return await self._refresh_with_notice(f"Updated risk '{updated.name}'.")

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
        if updated is None:
            return await self._refresh_with_notice("Failed to update component.", "error")
        return await self._refresh_with_notice("Component updated.")

    async def _delete_stage_with_confirmation(self, stage: Stage, args: list[str]) -> list[str]:
        if "--confirm" not in args:
            return ["Re-run with --confirm to delete the stage."]
        success = await delete_stage(UUID(str(stage.id)), self.env)
        if not success:
            return await self._refresh_with_notice("Stage delete failed.", "error")
        self._pop_focus_to_parent()
        return await self._refresh_with_notice("Stage deleted.")

    async def _delete_component_with_confirmation(
        self, component: Component, args: list[str]
    ) -> list[str]:
        if "--confirm" not in args:
            return ["Re-run with --confirm to delete the component."]
        success = await delete_component(UUID(str(component.id)), self.env)
        if not success:
            return await self._refresh_with_notice("Component delete failed.", "error")
        self._pop_focus_to_parent()
        return await self._refresh_with_notice("Component deleted.")

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
            return await self._refresh_with_notice("Nothing selected.", "warning")
        kind, _, raw_id = selected.item_id.partition(":")
        if kind == "component":
            link_id = await self._stage_component_link_id(stage, raw_id)
            if link_id is None:
                return await self._refresh_with_notice("Component not found.", "error")
            return self._start_confirm(
                f"Unassign {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_stage_component(link_id, self.env), "Component unassigned."
                ),
            )
        if kind == "ncrm":
            return self._start_confirm(
                f"Unassign {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_stage_ncrm(UUID(raw_id), self.env), "NCRM unassigned."
                ),
            )
        if kind == "risk":
            return self._start_confirm(
                f"Delete risk '{selected.label}'",
                lambda: self._unassign_with_notice(
                    delete_stage_risk(UUID(raw_id), self.env), "Risk deleted."
                ),
            )
        return await self._refresh_with_notice("Nothing to unassign.", "warning")

    async def _start_component_row_unassign(self, component: Component) -> list[str]:
        """Confirm-and-delete the caret-selected salt or risk row.

        Mirrors :meth:`_start_stage_row_unassign` for the component-focus page;
        ``^X`` deletes the component itself, this removes a single row.
        """
        del component  # The selected row carries the id; component scopes the screen.
        navigator = self.list_navigator
        selected = navigator.selected if navigator is not None else None
        if selected is None:
            return await self._refresh_with_notice("Nothing selected.", "warning")
        kind, _, raw_id = selected.item_id.partition(":")
        if kind == "salt":
            return self._start_confirm(
                f"Unassign salt {selected.label}",
                lambda: self._unassign_with_notice(
                    delete_component_salt(UUID(raw_id), self.env), "Salt unassigned."
                ),
            )
        if kind == "risk":
            return self._start_confirm(
                f"Delete risk '{selected.label}'",
                lambda: self._unassign_with_notice(
                    delete_component_risk(UUID(raw_id), self.env), "Risk deleted."
                ),
            )
        return await self._refresh_with_notice("Nothing to unassign.", "warning")

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
            return await self._refresh_with_notice("Unassign failed.", "error")
        return await self._refresh_with_notice(success)

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

    async def _create_material_from_prompt(self, payload: dict[str, str | None]) -> list[str]:
        created = await create_material(
            MaterialCreate(name=payload.get("name") or "", smiles=payload.get("smiles") or None),
            self.env,
        )
        if created is None:
            return await self._refresh_with_notice("Failed to create material.", "error")
        return await self._refresh_with_notice("Material created.")

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
        if created is None:
            return await self._refresh_with_notice("Failed to create NCRM entry.", "error")
        return await self._refresh_with_notice("NCRM entry created.")

    async def _create_counterion_from_prompt(self, payload: dict[str, str | None]) -> list[str]:
        created = await create_counterion(
            CounterionCreate(name=payload.get("name") or "", smiles=payload.get("smiles") or None),
            self.env,
        )
        if created is None:
            return await self._refresh_with_notice("Failed to create counterion.", "error")
        return await self._refresh_with_notice("Counterion created.")

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
            return await self._refresh_with_notice("Failed to create project.", "error")
        return await self._refresh_with_notice(f"Created project '{created.name}'.")

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
            return await self._refresh_with_notice("Failed to create process.", "error")
        return await self._refresh_with_notice(
            f"Created process {created.route_number}.{created.process_number}."
        )

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
                stoichiometry=_optional_float(payload.get("stoichiometry")),
                is_fully_defined=_optional_bool(payload.get("is_fully_defined")),
            ),
            self.env,
        )
        if created is None:
            return await self._refresh_with_notice("Failed to create salt record.", "error")
        return await self._refresh_with_notice("Created salt record.")

    async def _update_material_entry(
        self, item_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        updated = await update_material(
            UUID(item_id),
            MaterialUpdate(name=payload.get("name"), smiles=payload.get("smiles") or None),
            self.env,
        )
        if updated is None:
            return await self._refresh_with_notice("Failed to update material.", "error")
        return await self._refresh_with_notice("Material updated.")

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
        if updated is None:
            return await self._refresh_with_notice("Failed to update NCRM.", "error")
        return await self._refresh_with_notice("NCRM updated.")

    async def _update_counterion_entry(
        self, item_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        updated = await update_counterion(
            UUID(item_id),
            CounterionUpdate(name=payload.get("name"), smiles=payload.get("smiles") or None),
            self.env,
        )
        if updated is None:
            return await self._refresh_with_notice("Failed to update counterion.", "error")
        return await self._refresh_with_notice("Counterion updated.")

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
        """Frame the active guided prompt in a box matching the app aesthetic.

        Single-field choosers show just a ``Select {label}`` heading and the
        option list; multi-field forms show a labelled overview of every field
        (active marked ``▶``, completed showing values, pending dim). Live text
        input is typed on the bottom row, and the navigation hint is drawn there
        by the loop — neither is duplicated inside the box. A validation
        *message* is surfaced as a styled line above the box.
        """
        if self._prompt_state is None:
            return [message] if message else []
        state = self._prompt_state
        body = (
            self._single_field_body(state)
            if len(state.fields) == 1
            else self._multi_field_body(state)
        )
        boxed = render_box(body, max(self.screen.width - 2, 0), align="left", pad_x=2, pad_y=1)
        if message:
            return [self.screen.style_notice(message, "error"), "", *boxed]
        return boxed

    @property
    def _prompt_interior_width(self) -> int:
        """Return the printable width inside the prompt box (borders + padding)."""
        return max(self.screen.width - 2 - 2 * 2, 0)

    def _single_field_body(self, state: PromptState) -> list[str]:
        """Render a single-field chooser/prompt: a heading plus options or input."""
        current = state.current_field
        if state.is_select_field:
            navigator = state.select_navigator()
            options = (
                navigator.render_lines(self._prompt_interior_width, show_sections=False)
                if navigator
                else []
            )
            return [f"Select {current.label}", "", *options]
        return [f"Enter {current.label}"]

    def _multi_field_body(self, state: PromptState) -> list[str]:
        """Render a multi-field form as a labelled overview of every field."""
        lines: list[str] = []
        if state.title:
            lines.extend([self.screen.bold(state.title), ""])
        label_width = max(len(field_spec.label) for field_spec in state.fields)
        for index, field_spec in enumerate(state.fields):
            active = index == state.current_index
            marker = "▶" if active else " "
            value = state.collected[index]
            if value is not None:
                cell = value
            elif active and not state.is_select_field:
                cell = self.screen.dim("▏")
            else:
                cell = self.screen.dim("—")
            lines.append(f"{marker} {field_spec.label.ljust(label_width)}  {cell}")
        if state.is_select_field:
            navigator = state.select_navigator()
            if navigator is not None:
                lines.extend(
                    ["", *navigator.render_lines(self._prompt_interior_width, show_sections=False)]
                )
        return lines

    def _render_picker_lines(self) -> list[str]:
        if self._picker_state is None:
            return []
        # The filter query types on the bottom input row, so the hint lives
        # inside the box (it does not duplicate the bottom row, unlike prompts).
        body = [
            self._picker_state.label,
            "",
            *self._picker_state.navigator.render_lines(
                self._prompt_interior_width, show_sections=False
            ),
            "",
            self.screen.dim("Type to filter · Enter select · Esc cancel"),
        ]
        return render_box(body, max(self.screen.width - 2, 0), align="left", pad_x=2, pad_y=1)

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
                default=_default_text(risk.current_level),
            ),
            FieldSpec("proposed_mitigation", default=risk.proposed_mitigation),
            FieldSpec(
                "mitigated_level",
                field_type="select",
                options=LEVEL_OPTIONS,
                default=_default_text(risk.mitigated_level),
            ),
        ]

    def command_hints(self) -> str:
        """Return a single-line command hint for the current screen.

        Always reflects the active track's slash-commands from ``HELP_TOPICS``,
        independent of any modal or list-navigation state.
        """
        track = self.ctx.current.track
        keys = [*HELP_TOPICS.get(track, ["? help", "^C back"]), ": command"]
        return " · ".join(keys)

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


# Per-track hotkey legend shown on the bottom info line. Keys are Ctrl-<letter>
# combinations (rendered ``^X``) plus the always-available "/" search, "?" help,
# and ":" command line. ``handle_hotkey`` is the source of truth these describe.
HELP_TOPICS: dict[str, list[str]] = {
    "home": ["^A add project", "^B library", "^N admin", "/ search", "? help", "^D quit"],
    "project": ["^T routes", "^R risks", "^A add process", "^E edit", "^C back"],
    "route_select": ["↑↓ Enter open", "/ search", "^C back"],
    "route": [
        "^A add",
        "^F focus",
        "^E edit",
        "^X delete",
        "^L list",
        "^R risks",
        "/ search",
        "^C back",
    ],
    "stage_focus": [
        "^A add",
        "^L list",
        "^E edit",
        "^R risks",
        "^U unassign",
        "^X delete",
        "^C back",
    ],
    "component_focus": [
        "^A assign salt",
        "^E edit",
        "^U unassign",
        "^X delete",
        "^R risks",
        "^C back",
    ],
    "library": ["^A add", "^E edit", "^X delete", "^O show", "^F filter", "/ search", "^C back"],
    "admin": ["^A action", "^C back"],
    "risk_mode": ["^A add", "^E edit", "^L refresh", "^C back"],
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
