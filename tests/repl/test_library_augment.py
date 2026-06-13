"""Integration tests for the augment-on-add library flow.

Drives :class:`CommandDispatcher` through the material/NCRM add chain to verify
the Yes/No augment step: a successful resolve pre-fills the SMILES field and
persists the returned aliases, a miss falls back to manual entry, and "No"
keeps the manual path.
"""

import pytest

from riskmanager_cli.config.settings import Environment
from riskmanager_cli.database.db_session import get_db_session
from riskmanager_cli.model.tables import (
    Counterion,
    Material,
    MaterialAlias,
    NcrmLibrary,
    NcrmLibraryAlias,
)
from riskmanager_cli.operations.dmta_operations import ResolveResult
from riskmanager_cli.repl import commands
from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextManager
from riskmanager_cli.repl.session_state import SessionState


class _StubScreen:
    """Minimal screen stand-in exposing the styling hooks rendering touches."""

    width = 80

    @staticmethod
    def dim(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text

    @staticmethod
    def bold(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text

    @staticmethod
    def style_notice(message: str, level: str) -> str:
        """Return *message* unchanged (no terminal styling under test)."""
        del level
        return message


def _make_dispatcher(env: Environment) -> CommandDispatcher:
    """Build a dispatcher wired to a fresh context, session and stub screen."""
    return CommandDispatcher(
        ContextManager(), SessionState(), _StubScreen(), env  # type: ignore[arg-type]
    )


def _patch_resolve(monkeypatch: pytest.MonkeyPatch, result: ResolveResult) -> None:
    """Make the augment step return *result* without any network call."""

    async def fake_augment_name(name: str) -> ResolveResult:
        del name
        return result

    monkeypatch.setattr(commands, "augment_name", fake_augment_name)


async def _material(env: Environment, name: str) -> Material:
    async with get_db_session(env) as session:
        rows = await Material.get_where(session, Material.name == name)
        assert rows, f"material '{name}' was not created"
        return rows[0]


async def _material_aliases(env: Environment, material_id: str) -> list[str]:
    async with get_db_session(env) as session:
        rows = await MaterialAlias.get_where(session, MaterialAlias.material_id == material_id)
        return sorted(a.alias for a in rows)


@pytest.mark.integration
async def test_material_add_augment_yes_fills_smiles_and_aliases(
    temp_env: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing Yes fills the resolved SMILES (accepted as-is) and stores aliases."""
    _patch_resolve(
        monkeypatch,
        ResolveResult(
            name="aspirin",
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            aliases=["ASA", "2-acetoxybenzoic acid"],
            source="pubchem",
        ),
    )
    dispatcher = _make_dispatcher(temp_env)

    dispatcher._start_library_add_prompt("materials")  # pylint: disable=protected-access
    await dispatcher.advance_prompt("aspirin")  # name
    await dispatcher.advance_prompt("yes")  # augment? -> yes
    await dispatcher.advance_prompt("yes")  # confirm create (SMILES shown read-only)

    material = await _material(temp_env, "aspirin")
    assert material.smiles == "CC(=O)Oc1ccccc1C(=O)O"
    assert await _material_aliases(temp_env, str(material.id)) == [
        "2-acetoxybenzoic acid",
        "ASA",
    ]


@pytest.mark.integration
async def test_material_add_augment_unresolved_falls_back_to_manual(
    temp_env: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unresolved name leaves SMILES empty for manual entry and stores no aliases."""
    _patch_resolve(monkeypatch, ResolveResult(name="mystery"))
    dispatcher = _make_dispatcher(temp_env)

    dispatcher._start_library_add_prompt("materials")  # pylint: disable=protected-access
    await dispatcher.advance_prompt("mystery")  # name
    await dispatcher.advance_prompt("yes")  # augment? -> yes (but misses)
    await dispatcher.advance_prompt("C1CCCCC1")  # manual SMILES

    material = await _material(temp_env, "mystery")
    assert material.smiles == "C1CCCCC1"
    assert await _material_aliases(temp_env, str(material.id)) == []


@pytest.mark.integration
async def test_material_add_augment_no_keeps_manual_path(
    temp_env: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing No never calls augment_name and uses the manually entered SMILES."""

    async def fail_augment(name: str) -> ResolveResult:  # pragma: no cover - must not run
        raise AssertionError("augment_name should not be called when the user declines")

    monkeypatch.setattr(commands, "augment_name", fail_augment)
    dispatcher = _make_dispatcher(temp_env)

    dispatcher._start_library_add_prompt("materials")  # pylint: disable=protected-access
    await dispatcher.advance_prompt("benzene")  # name
    await dispatcher.advance_prompt("no")  # augment? -> no
    await dispatcher.advance_prompt("c1ccccc1")  # manual SMILES

    material = await _material(temp_env, "benzene")
    assert material.smiles == "c1ccccc1"
    assert await _material_aliases(temp_env, str(material.id)) == []


@pytest.mark.integration
async def test_ncrm_add_augment_uses_common_name_then_manual_display_name(
    temp_env: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NCRM augment keys off common_name; display_name is entered manually after."""
    _patch_resolve(
        monkeypatch,
        ResolveResult(
            name="methanol",
            smiles="CO",
            aliases=["MeOH"],
            source="dmta",
        ),
    )
    dispatcher = _make_dispatcher(temp_env)

    dispatcher._start_library_add_prompt("ncrm")  # pylint: disable=protected-access
    await dispatcher.advance_prompt("methanol")  # common_name (drives lookup)
    await dispatcher.advance_prompt("yes")  # augment? -> yes
    await dispatcher.advance_prompt("MeOH solvent")  # display_name (manual)
    await dispatcher.advance_prompt("true")  # interpret_chemically (SMILES shown read-only)

    async with get_db_session(temp_env) as session:
        entries = await NcrmLibrary.get_where(session, NcrmLibrary.common_name == "methanol")
        assert entries, "NCRM entry was not created"
        entry = entries[0]
        assert entry.display_name == "MeOH solvent"
        assert entry.smiles == "CO"
        assert entry.interpret_chemically is True
        aliases = await NcrmLibraryAlias.get_where(
            session, NcrmLibraryAlias.ncrm_library_id == entry.id
        )
        assert [a.alias for a in aliases] == ["MeOH"]


@pytest.mark.integration
async def test_ncrm_add_augment_shows_retrieved_values_readonly(
    temp_env: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a resolve, the finish form shows a read-only retrieved-values block."""
    _patch_resolve(
        monkeypatch,
        ResolveResult(
            name="chloroform",
            smiles="ClC(Cl)Cl",
            aliases=["Trichloromethane", "67-66-3"],
            source="pubchem",
        ),
    )
    dispatcher = _make_dispatcher(temp_env)

    dispatcher._start_library_add_prompt("ncrm")  # pylint: disable=protected-access
    await dispatcher.advance_prompt("chloroform")  # common_name (drives lookup)
    await dispatcher.advance_prompt("yes")  # augment? -> yes

    rendered = "\n".join(dispatcher._render_prompt_lines())  # pylint: disable=protected-access
    assert "Retrieved values (source: pubchem)" in rendered
    assert "chloroform" in rendered
    assert "ClC(Cl)Cl" in rendered
    assert "Trichloromethane, 67-66-3" in rendered
    assert "Remaining fields" in rendered
    assert "display_name" in rendered
    # The resolved SMILES is read-only now, not an editable remaining field.
    assert "smiles" not in rendered.split("Remaining fields", 1)[1]


@pytest.mark.integration
async def test_counterion_add_augment_confirm_creates_with_smiles_and_aliases(
    temp_env: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counterions have no remaining field, so a confirmation commits the resolve."""
    _patch_resolve(
        monkeypatch,
        ResolveResult(
            name="chloride",
            smiles="[Cl-]",
            aliases=["Cl"],
            source="pubchem",
        ),
    )
    dispatcher = _make_dispatcher(temp_env)

    dispatcher._start_library_add_prompt("counterions")  # pylint: disable=protected-access
    await dispatcher.advance_prompt("chloride")  # name (drives lookup)
    await dispatcher.advance_prompt("yes")  # augment? -> yes
    await dispatcher.advance_prompt("yes")  # confirm create

    async with get_db_session(temp_env) as session:
        rows = await Counterion.get_where(session, Counterion.name == "chloride")
        assert rows, "counterion was not created"
        assert rows[0].smiles == "[Cl-]"
