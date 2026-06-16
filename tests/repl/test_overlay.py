"""Unit tests for the overlay container (StackPane)."""

import pytest

from riskmanager_cli.repl.renderers.layout.geometry import visible_len
from riskmanager_cli.repl.renderers.layout.overlay import Placement, overlay


@pytest.mark.unit
def test_overlay_paints_corners_and_centre() -> None:
    """Each placement lands at its (halign, valign) anchor on the canvas."""
    canvas = overlay(
        5,
        3,
        [
            Placement(["A"], "left", "top"),
            Placement(["C"], "center", "middle"),
            Placement(["B"], "right", "bottom"),
        ],
    )
    assert canvas == ["A    ", "  C  ", "    B"]


@pytest.mark.unit
def test_overlay_produces_exact_dimensions() -> None:
    """An empty placement list yields a blank width × height canvas."""
    canvas = overlay(4, 2, [])
    assert canvas == ["    ", "    "]


@pytest.mark.unit
def test_overlay_later_placement_wins_on_overlap() -> None:
    """A later placement overrides an earlier one occupying the same cell."""
    canvas = overlay(3, 1, [Placement(["A"], "left", "top"), Placement(["B"], "left", "top")])
    assert canvas == ["B  "]


@pytest.mark.unit
def test_overlay_drops_overlapped_segment_wholesale() -> None:
    """An earlier segment a later one partially covers is dropped, never split."""
    canvas = overlay(3, 1, [Placement(["xxx"], "left", "top"), Placement(["Y"], "center", "top")])
    assert canvas == [" Y "]


@pytest.mark.unit
def test_overlay_measures_styled_blocks_by_visible_width() -> None:
    """A styled placement keeps the canvas the right printable width."""
    canvas = overlay(5, 1, [Placement(["\x1b[1mAB\x1b[0m"], "right", "top")])
    assert visible_len(canvas[0]) == 5
