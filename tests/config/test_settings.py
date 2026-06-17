"""Tests for ``config.settings.get_db_path`` (first-run path resolution)."""

from pathlib import Path

import pytest

from riskmanager_cli.config.settings import (
    Environment,
    get_db_path,
    get_structure_cache_dir,
)


@pytest.mark.unit
def test_get_db_path_uses_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DB_PATH", "/tmp/override.db")
    assert get_db_path(Environment.DEV) == Path("/tmp/override.db")
    assert get_db_path(Environment.PROD) == Path("/tmp/override.db")


@pytest.mark.unit
def test_get_db_path_in_memory_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DB_PATH", ":memory:")
    assert get_db_path(Environment.DEV) is None


@pytest.mark.unit
def test_get_db_path_prod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DB_PATH", raising=False)
    monkeypatch.setenv("APP_PROD_DB_PATH", "/data/prod.db")
    assert get_db_path(Environment.PROD) == Path("/data/prod.db")


@pytest.mark.unit
def test_get_db_path_dev_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DB_PATH", raising=False)
    monkeypatch.delenv("APP_DEV_DB_PATH", raising=False)
    assert get_db_path(Environment.DEV) == Path.home() / ".rmgr" / "database" / "riskmanager-dev.db"


@pytest.mark.unit
def test_get_db_path_prod_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DB_PATH", raising=False)
    monkeypatch.delenv("APP_PROD_DB_PATH", raising=False)
    assert get_db_path(Environment.PROD) == Path.home() / ".rmgr" / "database" / "riskmanager.db"


@pytest.mark.unit
def test_structure_cache_dir_honours_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "cache"
    monkeypatch.setenv("RMGR_STRUCTURE_CACHE_DIR", str(target))
    result = get_structure_cache_dir()
    assert result == target.resolve()
    assert result.is_dir()


@pytest.mark.unit
def test_structure_cache_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RMGR_STRUCTURE_CACHE_DIR", raising=False)
    assert get_structure_cache_dir() == (Path.home() / ".rmgr" / "structures").resolve()
