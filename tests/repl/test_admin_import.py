"""Integration tests for ``/admin import`` of counterions and NCRM entries.

Drives :class:`CommandDispatcher` end-to-end against a temp CSV to verify that
the ``aliases`` column is parsed (``;``-separated) and persisted as alias rows,
and that NCRM ``interpret_chemically`` is read from a ``true``/``false`` cell.
"""

from pathlib import Path

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.database.db_session import get_db_session
from riskmanager_cli.model.tables import (
    Counterion,
    CounterionAlias,
    NcrmLibrary,
    NcrmLibraryAlias,
)
from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextManager
from riskmanager_cli.repl.session_state import SessionState


class _StubScreen:
    """Minimal screen stand-in exposing the styling hooks rendering touches."""

    width = 80

    @staticmethod
    def style_notice(message: str, level: str) -> str:
        """Return *message* unchanged (no terminal styling under test)."""
        del level
        return message


def _make_dispatcher(env: Environment) -> CommandDispatcher:
    """Build a dispatcher wired to a fresh context, session and stub screen."""
    return CommandDispatcher(ContextManager(), SessionState(), _StubScreen(), env)  # type: ignore[arg-type]


async def _counterion_aliases(env: Environment, name: str) -> list[str]:
    """Return the sorted alias strings stored for the counterion named *name*."""
    async with get_db_session(env) as session:
        counterions = await Counterion.get_where(session, Counterion.name == name)
        assert counterions, f"counterion '{name}' was not created"
        aliases = await CounterionAlias.get_where(
            session, CounterionAlias.counterion_id == counterions[0].id
        )
        return sorted(a.alias for a in aliases)


@pytest.mark.integration
async def test_admin_import_counterions_loads_aliases(
    temp_env: Environment, tmp_path: Path
) -> None:
    """Counterion import splits the ``aliases`` column into alias rows."""
    csv_path = tmp_path / "counterions.csv"
    csv_path.write_text(
        "name,smiles,aliases\n"
        "methanesulfonate,CS(=O)(=O)[O-],Ms;methanesulfonic acid\n"
        "sulfate,,H2SO4\n",
        encoding="utf-8",
    )
    dispatcher = _make_dispatcher(temp_env)

    result = await dispatcher.dispatch(f"/admin import counterions {csv_path}")

    assert "created=2" in result[0]
    assert await _counterion_aliases(temp_env, "methanesulfonate") == [
        "Ms",
        "methanesulfonic acid",
    ]
    assert await _counterion_aliases(temp_env, "sulfate") == ["H2SO4"]


@pytest.mark.integration
async def test_admin_import_ncrm_loads_aliases_and_boolean(
    temp_env: Environment, tmp_path: Path
) -> None:
    """NCRM import reads the true/false boolean and the ``aliases`` column."""
    csv_path = tmp_path / "ncrm.csv"
    csv_path.write_text(
        "display_name,name,interpret_chemically,smiles,aliases\n"
        "(COCl)2,Oxalyl chloride,true,,oxalyl dichloride;ethanedioyl dichloride\n"
        "(+)-CSA,Camphorsulfonic acid,false,,\n",
        encoding="utf-8",
    )
    dispatcher = _make_dispatcher(temp_env)

    result = await dispatcher.dispatch(f"/admin import ncrm {csv_path}")

    assert "created=2" in result[0]
    async with get_db_session(temp_env) as session:
        entries = await NcrmLibrary.get_where(
            session, NcrmLibrary.display_name == "(COCl)2"
        )
        assert entries and entries[0].interpret_chemically is True
        aliases = await NcrmLibraryAlias.get_where(
            session, NcrmLibraryAlias.ncrm_library_id == entries[0].id
        )
        assert sorted(a.alias for a in aliases) == [
            "ethanedioyl dichloride",
            "oxalyl dichloride",
        ]
