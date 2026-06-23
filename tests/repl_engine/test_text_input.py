"""Unit tests for the cursor-aware :class:`LineEditor`."""

import pytest

from riskmanager_cli.repl_engine.text_input import LineEditor


@pytest.mark.unit
def test_from_text_places_cursor_at_end() -> None:
    """Seeding from text leaves the cursor after the last character."""
    editor = LineEditor.from_text("abc")
    assert (editor.text, editor.cursor) == ("abc", 3)


@pytest.mark.unit
def test_insert_at_cursor_advances_past_inserted_text() -> None:
    """Insertion lands at the cursor and moves it past the new characters."""
    editor = LineEditor.from_text("ac")
    editor.left()
    editor.insert("b")
    assert (editor.text, editor.cursor) == ("abc", 2)


@pytest.mark.unit
def test_backspace_deletes_before_cursor() -> None:
    """Backspace removes the character before the cursor."""
    editor = LineEditor(text="abc", cursor=2)
    editor.backspace()
    assert (editor.text, editor.cursor) == ("ac", 1)


@pytest.mark.unit
def test_backspace_at_start_is_a_noop() -> None:
    """Backspace at the start of the line changes nothing."""
    editor = LineEditor(text="abc", cursor=0)
    editor.backspace()
    assert (editor.text, editor.cursor) == ("abc", 0)


@pytest.mark.unit
def test_delete_removes_character_at_cursor() -> None:
    """Delete removes the character under the cursor without moving it."""
    editor = LineEditor(text="abc", cursor=1)
    editor.delete()
    assert (editor.text, editor.cursor) == ("ac", 1)


@pytest.mark.unit
def test_delete_at_end_is_a_noop() -> None:
    """Delete at the end of the line changes nothing."""
    editor = LineEditor.from_text("abc")
    editor.delete()
    assert (editor.text, editor.cursor) == ("abc", 3)


@pytest.mark.unit
def test_cursor_movement_clamps_to_bounds() -> None:
    """Left/right clamp at the ends; home/end jump to them."""
    editor = LineEditor(text="abc", cursor=1)
    editor.left()
    editor.left()
    assert editor.cursor == 0
    editor.right()
    editor.right()
    editor.right()
    editor.right()
    assert editor.cursor == 3
    editor.home()
    assert editor.cursor == 0
    editor.end()
    assert editor.cursor == 3
