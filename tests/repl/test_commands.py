"""Unit tests for repl command helpers: FieldSpec, PromptState, PickerState."""

import pytest

from riskmanager_cli.repl.commands import SCREEN_SPECS, CommandDispatcher
from riskmanager_cli.repl.context import ContextFrame, ContextManager
from riskmanager_cli.repl_engine.forms import FieldSpec, PickerState, PromptState
from riskmanager_cli.repl_engine.list_navigator import ListItem, ListNavigator


@pytest.mark.unit
def test_field_spec_text_accepts_non_empty_string() -> None:
    """A text FieldSpec stores a non-empty string value."""
    spec = FieldSpec(label="Name")
    state = PromptState(fields=[spec], collected=[None])
    done = state.submit_value("Aspirin")
    assert done is True
    assert state.collected[0] == "Aspirin"


@pytest.mark.unit
def test_field_spec_required_raises_on_empty_input() -> None:
    """Submitting an empty value for a required field raises ValueError."""
    spec = FieldSpec(label="Name", required=True)
    state = PromptState(fields=[spec], collected=[None])
    with pytest.raises(ValueError, match="required"):
        state.submit_value("")


@pytest.mark.unit
def test_field_spec_optional_stores_none_on_empty_input() -> None:
    """Submitting an empty value for an optional field stores None."""
    spec = FieldSpec(label="SMILES", required=False)
    state = PromptState(fields=[spec], collected=[None])
    state.submit_value("")
    assert state.collected[0] is None


@pytest.mark.unit
def test_field_spec_uses_default_when_empty_submitted() -> None:
    """Submitting empty input for a field with a default stores the default."""
    spec = FieldSpec(label="Level", field_type="int", default="5", required=False)
    state = PromptState(fields=[spec], collected=[None])
    state.submit_value("")
    assert state.collected[0] == "5"


@pytest.mark.unit
def test_field_spec_int_type_accepts_integer_string() -> None:
    """An int FieldSpec accepts a valid integer string and stores it as string."""
    spec = FieldSpec(label="Level", field_type="int")
    state = PromptState(fields=[spec], collected=[None])
    state.submit_value("7")
    assert state.collected[0] == "7"


@pytest.mark.unit
def test_field_spec_int_type_raises_on_non_integer() -> None:
    """An int FieldSpec raises ValueError for non-integer input."""
    spec = FieldSpec(label="Level", field_type="int")
    state = PromptState(fields=[spec], collected=[None])
    with pytest.raises(ValueError, match="integer"):
        state.submit_value("not_a_number")


@pytest.mark.unit
def test_field_spec_float_type_accepts_decimal_string() -> None:
    """A float FieldSpec accepts a valid decimal string and stores it as string."""
    spec = FieldSpec(label="Stoichiometry", field_type="float")
    state = PromptState(fields=[spec], collected=[None])
    state.submit_value("1.5")
    assert state.collected[0] == "1.5"


@pytest.mark.unit
def test_field_spec_float_type_raises_on_non_numeric() -> None:
    """A float FieldSpec raises ValueError for non-numeric input."""
    spec = FieldSpec(label="Stoichiometry", field_type="float")
    state = PromptState(fields=[spec], collected=[None])
    with pytest.raises(ValueError, match="number"):
        state.submit_value("not_a_number")


@pytest.mark.unit
def test_field_spec_select_type_accepts_value_text() -> None:
    """A select FieldSpec resolves typed text matching an option value."""
    spec = FieldSpec(label="Type", field_type="select", options=[("alpha", "a"), ("beta", "b")])
    state = PromptState(fields=[spec], collected=[None])
    state.submit_value("a")
    assert state.collected[0] == "a"


@pytest.mark.unit
def test_field_spec_select_type_accepts_label_text_case_insensitively() -> None:
    """A select FieldSpec resolves typed text matching an option label."""
    spec = FieldSpec(label="Type", field_type="select", options=[("Yes", "true"), ("No", "false")])
    state = PromptState(fields=[spec], collected=[None])
    state.submit_value("yes")
    assert state.collected[0] == "true"


@pytest.mark.unit
def test_field_spec_select_type_raises_on_unknown_text() -> None:
    """A select FieldSpec raises ValueError for text matching no option."""
    spec = FieldSpec(label="Type", field_type="select", options=[("alpha", "a"), ("beta", "b")])
    state = PromptState(fields=[spec], collected=[None])
    with pytest.raises(ValueError, match="must be one of"):
        state.submit_value("gamma")


@pytest.mark.unit
def test_select_field_submit_selection_stores_highlighted_value() -> None:
    """submit_selection stores the highlighted option's value, not its label."""
    spec = FieldSpec(label="Type", field_type="select", options=[("Yes", "true"), ("No", "false")])
    state = PromptState(fields=[spec], collected=[None])
    assert state.is_select_field is True
    state.move_selection("down")  # highlight "No"
    done = state.submit_selection()
    assert done is True
    assert state.collected[0] == "false"


@pytest.mark.unit
def test_select_field_default_highlights_matching_option() -> None:
    """A select field's default highlights the option storing that value."""
    spec = FieldSpec(
        label="Defined",
        field_type="select",
        options=[("Not specified", ""), ("Yes", "true"), ("No", "false")],
        default="true",
    )
    state = PromptState(fields=[spec], collected=[None])
    navigator = state.select_navigator()
    assert navigator is not None
    assert navigator.selected is not None
    assert navigator.selected.item_id == "true"


@pytest.mark.unit
def test_prompt_state_is_complete_when_all_fields_submitted() -> None:
    """is_complete() returns True once all fields have been submitted."""
    fields = [FieldSpec(label="A"), FieldSpec(label="B")]
    state = PromptState(fields=fields, collected=[None, None])
    assert state.is_complete() is False
    state.submit_value("value_a")
    assert state.is_complete() is False
    state.submit_value("value_b")
    assert state.is_complete() is True


@pytest.mark.unit
def test_prompt_state_as_dict_returns_label_keyed_values() -> None:
    """as_dict() returns collected values keyed by normalised field label."""
    fields = [FieldSpec(label="Risk Type"), FieldSpec(label="Name")]
    state = PromptState(fields=fields, collected=["Safety", "H2O"])
    result = state.as_dict()
    assert result["risk_type"] == "Safety"
    assert result["name"] == "H2O"


def _picker(*labels: str) -> PickerState:
    """Build a PickerState over the given item labels with a no-op callback."""
    items = [ListItem(label=label, item_id=label) for label in labels]
    return PickerState(label="Pick", all_items=items, on_select=lambda item: [item.item_id])


@pytest.mark.unit
def test_picker_empty_query_shows_all_items() -> None:
    """A freshly built picker highlights the first of all candidates."""
    picker = _picker("Caffeine", "Cafetannin", "Sodium")
    assert picker.selected is not None
    assert picker.selected.label == "Caffeine"


@pytest.mark.unit
def test_picker_set_query_filters_case_insensitively() -> None:
    """set_query narrows candidates by case-insensitive substring match."""
    picker = _picker("Caffeine", "Cafetannin", "Sodium")
    picker.set_query("CAF")
    assert picker.selected is not None
    assert picker.selected.label == "Caffeine"
    picker.move_down()
    assert picker.selected is not None
    assert picker.selected.label == "Cafetannin"


@pytest.mark.unit
def test_picker_query_with_no_matches_has_no_selection() -> None:
    """A query that matches nothing leaves the picker with no selection."""
    picker = _picker("Caffeine", "Sodium")
    picker.set_query("zzz")
    assert picker.selected is None


@pytest.mark.unit
def test_picker_move_up_wraps_to_last_match() -> None:
    """Moving up from the first match wraps to the last."""
    picker = _picker("Caffeine", "Cafetannin")
    picker.move_up()
    assert picker.selected is not None
    assert picker.selected.label == "Cafetannin"


def _nav_items() -> tuple[list[ListItem], list[ListItem]]:
    """Return (recents, all_items) for navigator preservation tests."""
    recents = [ListItem(label=f"r{i}", item_id=f"r{i}") for i in range(3)]
    all_items = [ListItem(label=f"a{i}", item_id=f"a{i}") for i in range(4)]
    return recents, all_items


@pytest.mark.unit
def test_navigator_selection_survives_rebuild_by_id() -> None:
    """Carrying the selected id into a rebuilt navigator preserves the cursor.

    This mirrors the arrow-key loop: a key press moves the live navigator, then
    the screen re-renders and rebuilds it. The rebuilt navigator must restore the
    previous selection rather than snap back to the first item.
    """
    recents, all_items = _nav_items()
    navigator = ListNavigator(recents, all_items)
    navigator.move_down()
    navigator.move_down()
    assert navigator.selected is not None
    moved_id = navigator.selected.item_id
    assert moved_id == "r2"

    rebuilt = ListNavigator(recents, all_items)
    rebuilt.select_item_id(moved_id)
    assert rebuilt.selected is not None
    assert rebuilt.selected.item_id == "r2"


@pytest.mark.unit
def test_navigator_crosses_recents_all_boundary() -> None:
    """Down from the last recent lands on the first all item, and up reverses."""
    recents, all_items = _nav_items()
    navigator = ListNavigator(recents, all_items)
    for _ in range(2):
        navigator.move_down()
    assert navigator.selected is not None
    assert navigator.selected.item_id == "r2"
    navigator.move_down()
    assert navigator.selected is not None
    assert navigator.selected.item_id == "a0"
    navigator.move_up()
    assert navigator.selected is not None
    assert navigator.selected.item_id == "r2"


@pytest.mark.unit
def test_render_lines_styles_and_aligns_subtitles() -> None:
    """With a styler, subtitles are aligned into a column and styled in place."""
    navigator = ListNavigator(
        [],
        [
            ListItem(label="A (RSM)", subtitle="Stage 1 reactant", item_id="1"),
            ListItem(label="A (Intermediate)", subtitle="unassigned", item_id="2"),
        ],
    )
    lines = navigator.render_lines(80, show_sections=False, subtitle_style=lambda text: f"<{text}>")

    assert lines[0].startswith("▶ A (RSM)")
    assert lines[0].endswith("<Stage 1 reactant>")
    assert lines[1].endswith("<unassigned>")
    # The styled subtitles start at the same column on every row.
    assert lines[0].index("<") == lines[1].index("<")


@pytest.mark.unit
def test_render_lines_without_styler_appends_plain_subtitle() -> None:
    """The legacy path leaves subtitles unstyled and space-appended."""
    navigator = ListNavigator([], [ListItem(label="Acme", subtitle="(recent)", item_id="1")])

    lines = navigator.render_lines(80, show_sections=False)

    assert lines == ["▶ Acme (recent)"]


# Maps a screen key to the context frame that produces it, so hint tests can
# exercise the library sub-modes (which share the ``library`` track).
_SCREEN_KEY_FRAMES: dict[str, ContextFrame] = {
    "library_home": ContextFrame(track="library", library_sub="select"),
    "library_list": ContextFrame(track="library", library_sub="materials"),
}

# Grammar tokens own the nav-hint line; none may leak onto the info line.
_GRAMMAR_TOKENS = ("↑↓", "navigate", "Enter", "/ search", ": command", "? help")


def _hints_dispatcher(screen_key: str) -> CommandDispatcher:
    """Build a dispatcher whose context resolves to *screen_key* for hint tests.

    ``command_hints`` only reads ``self.ctx`` and ``SCREEN_SPECS``, so the
    session/screen/env collaborators are unused and passed as ``None``.
    """
    ctx = ContextManager()
    frame = _SCREEN_KEY_FRAMES.get(screen_key)
    if frame is not None:
        ctx.push(frame)
    elif screen_key != "home":
        ctx.push(ContextFrame(track=screen_key))
    return CommandDispatcher(ctx, None, None, None)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize("screen_key", list(SCREEN_SPECS))
def test_command_hints_lists_actions_and_back(screen_key: str) -> None:
    """command_hints renders the screen's action hotkeys plus its back entry."""
    spec = SCREEN_SPECS[screen_key]
    hints = _hints_dispatcher(screen_key).command_hints()
    assert hints == " · ".join([*spec.actions, spec.back])


@pytest.mark.unit
@pytest.mark.parametrize("screen_key", list(SCREEN_SPECS))
def test_command_hints_excludes_grammar_tokens(screen_key: str) -> None:
    """The info line never repeats a nav-line grammar token (the iron-clad split)."""
    hints = _hints_dispatcher(screen_key).command_hints()
    assert not any(token in hints for token in _GRAMMAR_TOKENS)


@pytest.mark.unit
def test_command_hints_falls_back_for_unknown_screen() -> None:
    """An unknown screen yields just the generic back entry."""
    hints = _hints_dispatcher("does_not_exist").command_hints()
    assert hints == "^C back"


@pytest.mark.unit
@pytest.mark.parametrize("screen_key", ["route_select", "stage_focus", "risk_mode"])
def test_specs_define_previously_missing_screens(screen_key: str) -> None:
    """Every screen exposes a spec whose action entries are plain hotkeys."""
    entries = SCREEN_SPECS[screen_key].actions
    assert all(isinstance(entry, str) and entry for entry in entries)
    assert not any(entry.startswith(("/add", "/list")) for entry in entries)


class _StubScreen:
    """Minimal screen stand-in exposing the styling hooks rendering touches."""

    width = 80
    output_height = 40

    @staticmethod
    def dim(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text

    @staticmethod
    def bold(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text

    @staticmethod
    def reverse(text: str) -> str:
        """Bracket *text* so the in-field edit cursor is visible in assertions."""
        return f"[{text}]"


def _render_dispatcher() -> CommandDispatcher:
    """Build a dispatcher whose only used collaborator is the stub screen.

    ``_render_prompt_lines`` reads ``self.screen`` (width/dim/bold) and the
    active ``_prompt_state``; the context/session/env are unused for rendering.
    """
    return CommandDispatcher(ContextManager(), None, _StubScreen(), None)  # type: ignore[arg-type]


@pytest.mark.unit
def test_multi_field_form_shows_prefilled_default() -> None:
    """A pre-filled (defaulted) field shows its value in the multi-field form body."""
    dispatcher = _render_dispatcher()
    dispatcher.modal.start_prompt(
        [
            FieldSpec("display_name"),
            FieldSpec("smiles", required=False, default="CC(C)=O"),
        ],
        lambda **payload: [],
        title="Add NCRM",
    )
    rendered = "\n".join(dispatcher.modal._render_prompt_lines())  # pylint: disable=protected-access
    assert "CC(C)=O" in rendered


@pytest.mark.unit
def test_single_field_form_shows_prefilled_default() -> None:
    """A single-field edit form shows its pre-filled value in-place for editing."""
    dispatcher = _render_dispatcher()
    dispatcher.modal.start_prompt(
        [FieldSpec("smiles", required=False, default="CC(=O)O")],
        lambda **payload: [],
        title="Edit material",
    )
    # The loop seeds the editor from the field's default; render it in-place.
    rendered = "\n".join(dispatcher.modal.render_prompt("CC(=O)O", len("CC(=O)O")))
    assert "CC(=O)O" in rendered


@pytest.mark.unit
def test_active_field_wraps_long_value_in_place() -> None:
    """A long active value wraps across rows in-place; nothing is clipped."""
    dispatcher = _render_dispatcher()
    dispatcher.modal.start_prompt(
        [FieldSpec("smiles"), FieldSpec("name")],
        lambda **payload: [],
        title="Edit material",
    )
    long_value = "C" * 120
    rendered = dispatcher.modal.render_prompt(long_value, len(long_value))
    assert "".join(rendered).count("C") == 120
    assert sum(1 for line in rendered if "C" in line) >= 2


@pytest.mark.unit
def test_cursor_marks_active_character() -> None:
    """The edit cursor highlights the character it sits on, drawn in-place."""
    dispatcher = _render_dispatcher()
    dispatcher.modal.start_prompt(
        [FieldSpec("name"), FieldSpec("smiles")],
        lambda **payload: [],
        title="Edit material",
    )
    rendered = "\n".join(dispatcher.modal.render_prompt("hello", 1))
    assert "h[e]llo" in rendered
