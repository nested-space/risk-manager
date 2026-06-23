"""Guided-prompt and typeahead-picker engine for the terminal REPL.

This is the application-agnostic forms layer. It owns the field/prompt/picker
data types, their validation, and the modal lifecycle and rendering. The
application supplies field definitions (:class:`FieldSpec`) and callbacks; it
holds no knowledge of the domain being captured.

The :class:`ModalController` is the single owner of active modal state. The
event loop drives it through the controller protocol, and the application's
command dispatcher composes one and delegates its modal methods to it.
"""

from __future__ import annotations

import inspect
import textwrap
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .layout import render_box
from .list_navigator import ListItem, ListNavigator
from .screen import ScreenManager


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
        max_length: Optional cap on the number of characters that can be typed
            into a ``text`` field. ``None`` means no limit. Enforced by the REPL
            loop's input handler.
    """

    label: str
    field_type: str = "text"
    required: bool = True
    default: str | None = None
    options: list[tuple[str, str]] = field(default_factory=list)
    max_length: int | None = None


@dataclass
class InfoSection:
    """Read-only key/value rows shown above a form's editable fields.

    Attributes:
        title: Section heading (e.g. ``"Retrieved values (source: pubchem)"``).
        rows: ``(label, value)`` pairs rendered as non-editable lines.
    """

    title: str
    rows: list[tuple[str, str]]


def field_key(label: str) -> str:
    """Return the payload key a field *label* collects under.

    The completed-prompt payload is keyed by this normalised label, so callbacks
    can look up a value with the same transformation applied to the label they
    defined the field with.
    """
    return label.strip().lower().replace(" ", "_")


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


def _coerce_lines(result: Any) -> list[str]:
    """Normalise a callback result to a list of display lines."""
    if isinstance(result, list) and all(isinstance(item, str) for item in result):
        return result
    if isinstance(result, str):
        return [result]
    return [str(result)]


@dataclass
class PromptState:
    """Active guided prompt state."""

    fields: list[FieldSpec]
    collected: list[str | None]
    current_index: int = 0
    title: str | None = None
    info_section: InfoSection | None = None
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
            field_key(field_spec.label): self.collected[index]
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


class ModalController:
    """Own and drive the active guided prompt or typeahead picker.

    Why this exists:
        The modal lifecycle (collecting fields, filtering candidates, validating,
        cancelling, and invoking the completion callback) is identical for every
        form in the application. Centralising it here keeps the event loop and the
        command dispatcher free of modal bookkeeping: the loop forwards keystrokes
        and the dispatcher merely opens a modal with field specs and a callback.
    """

    def __init__(
        self,
        screen: ScreenManager,
        refresh: Callable[[str, str], Awaitable[list[str]]],
    ) -> None:
        """Create a modal controller.

        Args:
            screen: Screen manager, used for width-aware rendering and styling.
            refresh: Async hook returning the current screen's lines with a status
                notice ``(message, level)``; used when a modal is cancelled.
        """
        self._screen = screen
        self._refresh = refresh
        self._prompt_state: PromptState | None = None
        self._prompt_callback: Callable[..., Any] | None = None
        self._prompt_message: str | None = None
        self._picker_state: PickerState | None = None

    @property
    def prompt_state(self) -> PromptState | None:
        """Return the active guided prompt state, if any."""
        return self._prompt_state

    @property
    def picker_state(self) -> PickerState | None:
        """Return the active typeahead picker state, if any."""
        return self._picker_state

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

    def start_prompt(
        self,
        fields: list[FieldSpec],
        on_complete: Callable[..., Any],
        *,
        title: str | None = None,
        info_section: InfoSection | None = None,
    ) -> list[str]:
        """Enter guided prompt mode.

        Args:
            fields: Prompt field definitions.
            on_complete: Callback invoked once all values are collected.
            title: Optional form heading shown above multi-field forms.
            info_section: Optional read-only key/value block shown above the
                editable fields (e.g. augmentation results).

        Returns:
            Initial prompt-render lines.
        """
        self._prompt_state = PromptState(
            fields=fields,
            collected=[None] * len(fields),
            title=title,
            info_section=info_section,
        )
        self._prompt_callback = on_complete
        self._prompt_message = None
        return self._render_prompt_lines()

    def render_prompt(self, active_text: str, cursor: int) -> list[str]:
        """Re-render the active prompt with the live edit buffer shown in-place.

        The event loop owns the :class:`~.text_input.LineEditor` for the active
        text/numeric field and passes its ``text`` and ``cursor`` here on every
        edit, so the value is drawn inside the field box (wrapped, with a cursor)
        rather than on the bottom row. Any pending validation message is surfaced
        above the box.
        """
        return self._render_prompt_lines(self._prompt_message, active_text, cursor)

    def clear_prompt_message(self) -> None:
        """Drop any pending validation message (e.g. once the user edits again)."""
        self._prompt_message = None

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
            self._prompt_message = str(exc)
            return self._render_prompt_lines(str(exc))
        self._prompt_message = None
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
            self._prompt_message = str(exc)
            return self._render_prompt_lines(str(exc))
        self._prompt_message = None
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
            return _coerce_lines(awaited)
        return _coerce_lines(result)

    async def cancel_prompt(self) -> list[str]:
        """Cancel the active guided prompt and restore the current screen."""
        self._prompt_state = None
        self._prompt_callback = None
        self._prompt_message = None
        return await self._refresh("Cancelled.", "warning")

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
            return _coerce_lines(await result)
        return _coerce_lines(result)

    async def cancel_picker(self) -> list[str]:
        """Cancel the active typeahead picker and restore the current screen."""
        self._picker_state = None
        return await self._refresh("Cancelled.", "warning")

    def _render_prompt_lines(
        self, message: str | None = None, active_text: str = "", cursor: int = 0
    ) -> list[str]:
        """Frame the active guided prompt in a box matching the app aesthetic.

        Single-field choosers show just a ``Select {label}`` heading and the
        option list; multi-field forms show a labelled overview of every field
        (active marked ``▶``, completed showing values, pending dim). The active
        text/numeric field is edited in-place: *active_text* (the loop's live
        edit buffer) is drawn inside the field, wrapped across lines so the whole
        value stays visible, with the edit cursor at *cursor*. The navigation
        hint is drawn on the bottom row by the loop. A validation *message* is
        surfaced as a styled line above the box.
        """
        if self._prompt_state is None:
            return [message] if message else []
        state = self._prompt_state
        body = (
            self._single_field_body(state, active_text, cursor)
            if len(state.fields) == 1
            else self._multi_field_body(state, active_text, cursor)
        )
        prefix: list[str] = []
        # Preserve current behavior: single-field forms without an info section
        # show no title (today's _single_field_body ignores it). A title is drawn
        # for multi-field forms and for any form carrying a read-only section.
        if state.title and (len(state.fields) > 1 or state.info_section is not None):
            prefix += [self._screen.bold(state.title), ""]
        if state.info_section is not None:
            prefix += self._info_section_lines(state.info_section, state)
            prefix += ["", self._screen.dim("Remaining fields"), ""]
        body = [*prefix, *body]
        boxed = render_box(body, max(self._screen.width - 2, 0), align="left", pad_x=2, pad_y=1)
        if message:
            return [self._screen.style_notice(message, "error"), "", *boxed]
        return boxed

    @property
    def _prompt_interior_width(self) -> int:
        """Return the printable width inside the prompt box (borders + padding)."""
        return max(self._screen.width - 2 - 2 * 2, 0)

    def _single_field_body(self, state: PromptState, active_text: str, cursor: int) -> list[str]:
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
        rows = self._render_editable_value(active_text, cursor, self._prompt_interior_width)
        return [f"Enter {current.label}", "", *rows]

    def _info_section_lines(self, section: InfoSection, state: PromptState) -> list[str]:
        """Render a read-only key/value block, aligned with the editable fields.

        Row labels share a column width with the form's field labels so the value
        columns line up, and rows are indented two spaces to sit under the ``▶ ``
        marker column of the editable fields below.
        """
        width = self._form_label_width(state)
        lines = [self._screen.dim(section.title)]
        for label, value in section.rows:
            lines.append(f"  {self._screen.dim(label.ljust(width))}  {value}")
        return lines

    @staticmethod
    def _form_label_width(state: PromptState) -> int:
        """Return the shared label column width for info rows and editable fields."""
        labels = [field_spec.label for field_spec in state.fields]
        if state.info_section is not None:
            labels += [label for label, _ in state.info_section.rows]
        return max((len(label) for label in labels), default=0)

    def _multi_field_body(self, state: PromptState, active_text: str, cursor: int) -> list[str]:
        """Render a multi-field form as a labelled overview of every field.

        The active text field is edited in-place and wrapped; every other field
        shows its collected value or dimmed default, also wrapped so long values
        (e.g. a SMILES string) stay fully visible across continuation lines.
        """
        lines: list[str] = []
        label_width = self._form_label_width(state)
        value_width = max(self._prompt_interior_width - (label_width + 4), 1)
        indent = " " * (label_width + 4)
        for index, field_spec in enumerate(state.fields):
            active = index == state.current_index
            marker = "▶" if active else " "
            editing = active and field_spec.field_type != "select"
            rows = self._field_cell_rows(
                field_spec,
                value=state.collected[index],
                active_edit=(active_text, cursor) if editing else None,
                width=value_width,
            )
            lines.append(f"{marker} {field_spec.label.ljust(label_width)}  {rows[0]}")
            lines.extend(f"{indent}{row}" for row in rows[1:])
        if state.is_select_field:
            navigator = state.select_navigator()
            if navigator is not None:
                lines.extend(
                    ["", *navigator.render_lines(self._prompt_interior_width, show_sections=False)]
                )
        return lines

    def _field_cell_rows(
        self,
        field_spec: FieldSpec,
        *,
        value: str | None,
        active_edit: tuple[str, int] | None,
        width: int,
    ) -> list[str]:
        """Return the wrapped value row(s) for one form field.

        When *active_edit* is the active field's ``(text, cursor)`` the value is
        drawn in-place with the edit cursor; otherwise the collected value or
        dimmed default is wrapped, falling back to ``—`` until collected.
        """
        if active_edit is not None:
            return self._render_editable_value(active_edit[0], active_edit[1], width)
        if value is not None:
            return self._wrap_plain(value, width)
        if field_spec.default is not None and field_spec.field_type != "select":
            return [self._screen.dim(row) for row in self._wrap_plain(field_spec.default, width)]
        return [self._screen.dim("—")]

    @staticmethod
    def _wrap_plain(value: str, width: int) -> list[str]:
        """Hard-wrap *value* to *width* columns, never returning an empty list."""
        return textwrap.wrap(value, width=max(width, 1)) or [value]

    def _render_editable_value(self, text: str, cursor: int, width: int) -> list[str]:
        """Render *text* hard-wrapped to *width* with a reverse-video edit cursor.

        Hard wrapping (fixed *width* chunks, not word wrapping) keeps every
        character at a deterministic position so *cursor* maps cleanly onto a
        wrapped row and column. The cursor highlights the character it sits on,
        or a trailing space when it rests at the end of the value.
        """
        width = max(width, 1)
        rows = [text[i : i + width] for i in range(0, len(text), width)] or [""]
        row_index, col = divmod(cursor, width)
        while row_index >= len(rows):
            rows.append("")
        rows[row_index] = self._cursor_row(rows[row_index], col)
        return rows

    def _cursor_row(self, row: str, col: int) -> str:
        """Return *row* with the edit cursor drawn at column *col*."""
        if col < len(row):
            return f"{row[:col]}{self._screen.reverse(row[col])}{row[col + 1 :]}"
        return f"{row}{self._screen.reverse(' ')}"

    def _render_picker_lines(self) -> list[str]:
        if self._picker_state is None:
            return []
        # The filter query types on the bottom input row, so the hint lives
        # inside the box (it does not duplicate the bottom row, unlike prompts).
        body = [
            self._picker_state.label,
            "",
            *self._picker_state.navigator.render_lines(
                self._prompt_interior_width,
                show_sections=False,
                subtitle_style=self._screen.dim,
            ),
            "",
            self._screen.dim("Type to filter · Enter select · Esc cancel"),
        ]
        return render_box(body, max(self._screen.width - 2, 0), align="left", pad_x=2, pad_y=1)
