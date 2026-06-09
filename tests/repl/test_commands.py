"""Unit tests for repl command helpers: FieldSpec, PromptState."""

import pytest

from riskmanager_cli.repl.commands import FieldSpec, PromptState


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
def test_field_spec_choice_type_accepts_valid_choice() -> None:
    """A choice FieldSpec accepts a matching choice value."""
    spec = FieldSpec(label="Type", field_type="choice", choices=["alpha", "beta"])
    state = PromptState(fields=[spec], collected=[None])
    state.submit_value("alpha")
    assert state.collected[0] == "alpha"


@pytest.mark.unit
def test_field_spec_choice_type_is_case_insensitive() -> None:
    """A choice FieldSpec matches choices case-insensitively."""
    spec = FieldSpec(label="Type", field_type="choice", choices=["Alpha", "Beta"])
    state = PromptState(fields=[spec], collected=[None])
    state.submit_value("ALPHA")
    assert state.collected[0] == "Alpha"


@pytest.mark.unit
def test_field_spec_choice_type_raises_on_invalid_choice() -> None:
    """A choice FieldSpec raises ValueError for a value not in the choices."""
    spec = FieldSpec(label="Type", field_type="choice", choices=["alpha", "beta"])
    state = PromptState(fields=[spec], collected=[None])
    with pytest.raises(ValueError, match="must be one of"):
        state.submit_value("gamma")


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
