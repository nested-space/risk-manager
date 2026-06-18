"""Unit tests for the layout content widgets (title, subtitle, text area, card)."""

import pytest

from riskmanager_cli.repl_engine.layout.geometry import block_width, visible_len
from riskmanager_cli.repl_engine.layout.widgets import (
    bullet_list,
    card,
    subtitle,
    text_area,
    title,
)


@pytest.mark.unit
def test_title_underlines_to_visible_width() -> None:
    """The underline matches the title's printable width, ignoring ANSI."""
    assert title("Hello") == ["Hello", "─────"]
    styled = title("\x1b[1mHi\x1b[0m")
    assert styled[1] == "──"


@pytest.mark.unit
def test_subtitle_is_a_single_section_rule() -> None:
    """A subtitle is one section-rule line carrying the heading."""
    rule = subtitle("Details", 80)
    assert len(rule) == 1
    assert rule[0].startswith("─ Details ")


@pytest.mark.unit
def test_text_area_wraps_to_width() -> None:
    """A paragraph wraps so no line exceeds the requested width."""
    lines = text_area("the quick brown fox jumps over the lazy dog", 12)
    assert all(visible_len(line) <= 12 for line in lines)
    assert len(lines) > 1


@pytest.mark.unit
def test_bullet_list_uses_hanging_indent() -> None:
    """Bullets keep the marker in the gutter; continuations align under the text."""
    lines = bullet_list(["alpha beta gamma delta epsilon"], 12)
    assert lines[0].startswith("• ")
    assert all(line.startswith("  ") for line in lines[1:])


@pytest.mark.unit
def test_card_frames_heading_over_body() -> None:
    """A card frames the heading, a blank separator, then the body, all at width."""
    box = card("Title", ["body"], width=20, pad_y=1)
    assert all(visible_len(line) == 20 for line in box)
    assert box[0].startswith("┌") and box[-1].startswith("└")
    text = "\n".join(box)
    assert "Title" in text
    assert "body" in text


@pytest.mark.unit
def test_card_without_body_holds_only_heading() -> None:
    """An omitted body frames just the heading."""
    box = card("Solo", width=12)
    assert block_width(box) == 12
    assert "Solo" in "\n".join(box)
