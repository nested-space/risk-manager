"""Unit tests for riskmanager_cli.repl.session_state."""

import json
from pathlib import Path

import pytest

from riskmanager_cli.repl.session_state import SessionState


@pytest.mark.unit
def test_load_from_missing_file_returns_defaults(tmp_path: Path) -> None:
    """Loading a non-existent path silently returns a default SessionState."""
    path = tmp_path / "nonexistent.json"
    state = SessionState.load(path=path)
    assert state.recent_projects == []
    assert state.recent_routes == {}


@pytest.mark.unit
def test_load_from_corrupt_file_returns_defaults(tmp_path: Path) -> None:
    """Loading malformed JSON silently returns a default SessionState."""
    path = tmp_path / "session.json"
    path.write_text("{ invalid json !!!", encoding="utf-8")
    state = SessionState.load(path=path)
    assert state.recent_projects == []


@pytest.mark.unit
def test_save_and_load_round_trips_recent_projects(tmp_path: Path) -> None:
    """A saved recent_projects list survives a reload from disk."""
    path = tmp_path / "session.json"
    state = SessionState(path=path)
    state.recent_projects = ["uuid-1", "uuid-2"]
    state.save()
    loaded = SessionState.load(path=path)
    assert loaded.recent_projects == ["uuid-1", "uuid-2"]


@pytest.mark.unit
def test_push_project_inserts_at_front_of_list() -> None:
    """push_project() prepends the project UUID."""
    state = SessionState(recent_projects=["uuid-old"])
    state.push_project("uuid-new")
    assert state.recent_projects[0] == "uuid-new"


@pytest.mark.unit
def test_push_project_deduplicates_existing_entry() -> None:
    """push_project() removes an existing occurrence before prepending."""
    state = SessionState(recent_projects=["uuid-1", "uuid-2"])
    state.push_project("uuid-2")
    assert state.recent_projects == ["uuid-2", "uuid-1"]


@pytest.mark.unit
def test_push_project_caps_list_at_five() -> None:
    """recent_projects never exceeds five entries."""
    state = SessionState()
    for i in range(7):
        state.push_project(f"uuid-{i}")
    assert len(state.recent_projects) == 5
    assert state.recent_projects[0] == "uuid-6"


@pytest.mark.unit
def test_push_route_records_per_project() -> None:
    """push_route() tracks routes separately per project."""
    state = SessionState()
    state.push_route("proj-1", "route-a")
    state.push_route("proj-2", "route-b")
    assert "route-a" in state.recent_routes.get("proj-1", [])
    assert "route-b" in state.recent_routes.get("proj-2", [])


@pytest.mark.unit
def test_push_route_caps_per_project_at_three() -> None:
    """Recent routes per project are capped at three entries."""
    state = SessionState()
    for i in range(5):
        state.push_route("proj-1", f"route-{i}")
    assert len(state.recent_routes["proj-1"]) == 3
    assert state.recent_routes["proj-1"][0] == "route-4"


@pytest.mark.unit
def test_update_context_updates_known_keys() -> None:
    """update_context() sets recognised context keys."""
    state = SessionState()
    state.update_context(track="project", project_id="uuid-proj")
    assert state.last_context["track"] == "project"
    assert state.last_context["project_id"] == "uuid-proj"


@pytest.mark.unit
def test_update_context_ignores_unknown_keys() -> None:
    """update_context() silently discards unrecognised key names."""
    state = SessionState()
    state.update_context(nonexistent_key="value")
    assert "nonexistent_key" not in state.last_context


@pytest.mark.unit
def test_save_omits_empty_route_projects(tmp_path: Path) -> None:
    """Routes for a project with an empty list are omitted from the saved file."""
    path = tmp_path / "session.json"
    state = SessionState(path=path, recent_routes={"proj-1": [], "proj-2": ["route-a"]})
    state.save()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "proj-1" not in raw["recent_routes"]
    assert "proj-2" in raw["recent_routes"]
