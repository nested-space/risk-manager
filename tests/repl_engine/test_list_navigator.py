"""Unit tests for the list navigator's paging move."""

import pytest

from riskmanager_cli.repl_engine.list_navigator import ListItem, ListNavigator


def _nav(count: int) -> ListNavigator:
    """Build a navigator over *count* items keyed by their index."""
    return ListNavigator([], [ListItem(label=str(i), item_id=str(i)) for i in range(count)])


@pytest.mark.unit
def test_move_steps_by_delta_without_wrapping() -> None:
    """A positive delta moves the selection down by that many items."""
    nav = _nav(10)
    nav.move(3)
    assert nav.selected is not None
    assert nav.selected.item_id == "3"


@pytest.mark.unit
def test_move_clamps_to_last_item() -> None:
    """Overshooting the end lands on the last item, not wrapping to the start."""
    nav = _nav(5)
    nav.move(10)
    assert nav.selected is not None
    assert nav.selected.item_id == "4"


@pytest.mark.unit
def test_move_clamps_to_first_item() -> None:
    """Overshooting the start lands on the first item, not wrapping to the end."""
    nav = _nav(5)
    nav.move(3)
    nav.move(-10)
    assert nav.selected is not None
    assert nav.selected.item_id == "0"


@pytest.mark.unit
def test_move_on_empty_list_is_noop() -> None:
    """Moving an empty navigator leaves it with no selection."""
    nav = ListNavigator([], [])
    nav.move(3)
    assert nav.selected is None
