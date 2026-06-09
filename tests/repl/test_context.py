"""Unit tests for governance_cli.repl.context."""

import pytest

from governance_cli.repl.context import ContextFrame, ContextManager


@pytest.mark.unit
def test_context_manager_initial_track_is_home() -> None:
    """A freshly created ContextManager starts at the home track."""
    ctx = ContextManager()
    assert ctx.current.track == "home"


@pytest.mark.unit
def test_push_adds_frame_to_stack() -> None:
    """push() makes the new frame the current context."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="project", project_name="Alpha"))
    assert ctx.current.track == "project"
    assert ctx.current.project_name == "Alpha"


@pytest.mark.unit
def test_pop_removes_top_frame_and_returns_it() -> None:
    """pop() removes the topmost frame and returns it."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="project", project_name="Alpha"))
    popped = ctx.pop()
    assert popped is not None
    assert popped.track == "project"
    assert ctx.current.track == "home"


@pytest.mark.unit
def test_pop_at_root_returns_none() -> None:
    """pop() returns None when already at the root (home) frame."""
    ctx = ContextManager()
    result = ctx.pop()
    assert result is None
    assert ctx.current.track == "home"


@pytest.mark.unit
def test_reset_returns_stack_to_home() -> None:
    """reset() clears all pushed frames and restores the home frame."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="project"))
    ctx.push(ContextFrame(track="route"))
    ctx.reset()
    assert ctx.current.track == "home"
    assert ctx.pop() is None  # stack depth is 1 after reset


@pytest.mark.unit
def test_breadcrumb_at_home_returns_home_label() -> None:
    """breadcrumb() returns '[ Home ]' when at the home track."""
    ctx = ContextManager()
    assert ctx.breadcrumb() == "[ Home ]"


@pytest.mark.unit
def test_breadcrumb_at_project_includes_project_name() -> None:
    """breadcrumb() includes the project name in project track."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="project", project_name="Alpha"))
    assert "Alpha" in ctx.breadcrumb()


@pytest.mark.unit
def test_breadcrumb_at_route_includes_route_label() -> None:
    """breadcrumb() includes the route label in route track."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="route", project_name="Alpha", route_label="1.1"))
    crumb = ctx.breadcrumb()
    assert "Alpha" in crumb
    assert "1.1" in crumb


@pytest.mark.unit
def test_breadcrumb_at_stage_focus_includes_stage_name() -> None:
    """breadcrumb() includes stage name in stage_focus track."""
    ctx = ContextManager()
    ctx.push(
        ContextFrame(
            track="stage_focus",
            project_name="Alpha",
            route_label="1.1",
            stage_name="Reaction",
        )
    )
    crumb = ctx.breadcrumb()
    assert "Reaction" in crumb


@pytest.mark.unit
def test_breadcrumb_at_risk_mode_shows_risks_label() -> None:
    """breadcrumb() appends '[ Risks ]' in risk_mode track."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="project", project_name="Alpha"))
    ctx.push(ContextFrame(track="risk_mode"))
    assert "Risks" in ctx.breadcrumb()


@pytest.mark.unit
def test_mode_label_reflects_current_track() -> None:
    """mode_label() returns a string containing the current track name."""
    ctx = ContextManager()
    ctx.push(ContextFrame(track="library"))
    assert "library" in ctx.mode_label()
