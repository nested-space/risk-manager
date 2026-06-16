"""Unit tests for the box-drawn TabPane container."""

import pytest

from riskmanager_cli.repl.renderers.layout.geometry import visible_len
from riskmanager_cli.repl.renderers.layout.tabpane import tabpane

_TABS = ["Alpha", "Beta"]
_BODY = ["one", "two"]


@pytest.mark.unit
def test_tabpane_lines_share_one_visible_width() -> None:
    """Every rendered line is exactly the pane width (top, labels, body, bottom)."""
    pane = tabpane(_TABS, 0, _BODY, width=40)
    assert all(visible_len(line) == 40 for line in pane)
    # 3 header rows (tops, labels, connector) + body + 1 bottom border.
    assert len(pane) == 3 + len(_BODY) + 1


@pytest.mark.unit
def test_tabpane_draws_all_labels_and_body() -> None:
    """Both tab labels and the body content appear in the pane."""
    text = "\n".join(tabpane(_TABS, 1, _BODY, width=40))
    for label in _TABS:
        assert label in text
    assert "one" in text and "two" in text


@pytest.mark.unit
@pytest.mark.parametrize("active", [0, 1])
def test_tabpane_active_tab_opens_into_body(active: int) -> None:
    """The active tab's underline is an open notch; inactive tabs stay closed."""
    pane = tabpane(_TABS, active, _BODY, width=40)
    labels, connector = pane[1], pane[2]
    open_label = _TABS[active]
    closed_label = _TABS[1 - active]
    # Under the active label the connector is open (space); under the inactive
    # label it is a drawn border (─).
    assert connector[labels.index(open_label)] == " "
    assert connector[labels.index(closed_label)] == "─"


@pytest.mark.unit
def test_tabpane_emphasises_only_the_active_label() -> None:
    """The active label cell is styled; the inactive one is left plain."""
    pane = tabpane(_TABS, 0, _BODY, width=40, emphasize=lambda s: f"<{s}>")
    labels = pane[1]
    assert "<" in labels
    assert "< Beta >" not in labels  # only the active "Alpha" cell is wrapped
    assert "Beta" in labels


@pytest.mark.unit
def test_tabpane_widens_to_fit_tab_strip() -> None:
    """When the requested width is below the tab strip, the pane uses the strip."""
    pane = tabpane(["Libraries", "Information"], 0, ["x"], width=5)
    # Tab strip: " Libraries "(11) + " Information "(13) + 3 separators = 27.
    assert all(visible_len(line) == 27 for line in pane)
