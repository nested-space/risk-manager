"""Unit tests for :mod:`riskmanager_cli.service.structure_viewer`.

The cheminformatics render call, viewer discovery and subprocess launch are all
patched so each :class:`StructureResult` branch is exercised without RDKit
rendering or spawning a real viewer.
"""

import hashlib
from pathlib import Path

import pytest

from riskmanager_cli.service import structure_viewer
from riskmanager_cli.service.structure_viewer import StructureResult, find_viewer, show_structure

_SMILES = "CC(=O)C"


def _expected_cache_path(cache_dir: Path) -> Path:
    """Return the PNG path :func:`show_structure` derives for :data:`_SMILES`."""
    return cache_dir / f"{hashlib.sha256(_SMILES.encode()).hexdigest()}.png"


@pytest.fixture(autouse=True)
def _cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the structure cache at an isolated temp directory for every test."""
    monkeypatch.setenv("RMGR_STRUCTURE_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("RMGR_IMAGE_VIEWER", raising=False)
    return tmp_path


@pytest.mark.unit
def test_find_viewer_honours_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RMGR_IMAGE_VIEWER", "my-viewer")
    assert find_viewer() == "my-viewer"


@pytest.mark.unit
def test_find_viewer_returns_first_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(structure_viewer.shutil, "which", lambda name: name == "xdg-open")
    assert find_viewer() == "xdg-open"


@pytest.mark.unit
def test_find_viewer_returns_none_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(structure_viewer.shutil, "which", lambda _name: None)
    assert find_viewer() is None


@pytest.mark.unit
def test_show_structure_ok(monkeypatch: pytest.MonkeyPatch, _cache_dir: Path) -> None:
    calls: list[list[str]] = []

    def fake_render(smiles: str, **kwargs: object) -> None:
        Path(str(kwargs["out_path"])).write_bytes(b"png")

    monkeypatch.setattr(structure_viewer.dmta_cli, "render", fake_render)
    monkeypatch.setattr(structure_viewer.shutil, "which", lambda name: name == "feh")
    monkeypatch.setattr(
        structure_viewer.subprocess, "Popen", lambda args, **_kw: calls.append(args)
    )

    assert show_structure(_SMILES) is StructureResult.OK
    assert calls == [["feh", str(_expected_cache_path(_cache_dir))]]


@pytest.mark.unit
def test_show_structure_skips_render_when_cached(
    monkeypatch: pytest.MonkeyPatch, _cache_dir: Path
) -> None:
    _expected_cache_path(_cache_dir).write_bytes(b"png")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("render must not be called when the PNG is cached")

    monkeypatch.setattr(structure_viewer.dmta_cli, "render", boom)
    monkeypatch.setattr(structure_viewer.shutil, "which", lambda name: name == "feh")
    monkeypatch.setattr(structure_viewer.subprocess, "Popen", lambda *_a, **_kw: None)

    assert show_structure(_SMILES) is StructureResult.OK


@pytest.mark.unit
def test_show_structure_render_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise ValueError("invalid SMILES")

    monkeypatch.setattr(structure_viewer.dmta_cli, "render", boom)
    assert show_structure("not-a-smiles") is StructureResult.RENDER_FAILED


@pytest.mark.unit
def test_show_structure_no_viewer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(structure_viewer.dmta_cli, "render", lambda *_a, **_kw: None)
    monkeypatch.setattr(structure_viewer.shutil, "which", lambda _name: None)
    assert show_structure(_SMILES) is StructureResult.NO_VIEWER


@pytest.mark.unit
def test_show_structure_launch_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("cannot spawn")

    monkeypatch.setattr(structure_viewer.dmta_cli, "render", lambda *_a, **_kw: None)
    monkeypatch.setattr(structure_viewer.shutil, "which", lambda name: name == "feh")
    monkeypatch.setattr(structure_viewer.subprocess, "Popen", boom)
    assert show_structure(_SMILES) is StructureResult.LAUNCH_FAILED
