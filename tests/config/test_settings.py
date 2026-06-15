"""Tests for ``config.settings.get_db_path`` (first-run path resolution)."""

from pathlib import Path

import pytest

from riskmanager_cli.config.settings import Environment, get_db_path


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
    assert get_db_path(Environment.DEV) == Path("./riskmanager-dev.db")
