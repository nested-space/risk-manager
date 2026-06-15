"""Tests for first-run detection and bootstrap seeding (``repl/bootstrap``)."""

import blessed
import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.database.db_session import get_db_session
from riskmanager_cli.model.tables import Counterion, NcrmLibrary
from riskmanager_cli.repl.bootstrap import is_first_run, run_first_time_setup


@pytest.mark.unit
def test_is_first_run_true_when_file_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    db_path = f"{tmp_path}/absent.db"
    monkeypatch.setenv("APP_DB_PATH", db_path)
    assert is_first_run(Environment.DEV) is True


@pytest.mark.unit
def test_is_first_run_false_when_file_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    db_file = f"{tmp_path}/present.db"
    with open(db_file, "w", encoding="utf-8") as handle:
        handle.write("")
    monkeypatch.setenv("APP_DB_PATH", db_file)
    assert is_first_run(Environment.DEV) is False


@pytest.mark.unit
def test_is_first_run_false_for_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DB_PATH", ":memory:")
    assert is_first_run(Environment.DEV) is False


@pytest.mark.integration
async def test_run_first_time_setup_creates_and_seeds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = f"{tmp_path}/fresh.db"
    monkeypatch.setenv("APP_DB_PATH", db_path)
    term = blessed.Terminal()

    await run_first_time_setup(term, Environment.DEV)

    async with get_db_session(Environment.DEV) as session:
        assert len(await Counterion.get_all(session)) == 24
        assert len(await NcrmLibrary.get_all(session)) == 325

    output = capsys.readouterr().out
    assert "Initialising" in output
