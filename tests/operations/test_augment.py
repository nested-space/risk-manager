"""Unit tests for riskmanager_cli.operations.dmta_operations.augment_name."""

import dmta_cli
import pytest

from riskmanager_cli.operations.dmta_operations import ResolveResult, augment_name


async def test_augment_name_returns_resolved_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful resolve is passed through with smiles, aliases, and source."""
    resolved = ResolveResult(
        name="aspirin",
        smiles="CC(=O)Oc1ccccc1C(=O)O",
        aliases=["2-acetoxybenzoic acid", "ASA"],
        source="pubchem",
    )

    async def fake_aresolve(name: str) -> ResolveResult:
        assert name == "aspirin"
        return resolved

    monkeypatch.setattr(dmta_cli, "aresolve", fake_aresolve)

    result = await augment_name("aspirin")

    assert result is resolved
    assert result.resolved is True
    assert result.smiles == "CC(=O)Oc1ccccc1C(=O)O"
    assert result.aliases == ["2-acetoxybenzoic acid", "ASA"]
    assert result.source == "pubchem"


async def test_augment_name_returns_unresolved_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unresolved name yields a result whose ``resolved`` is False."""
    unresolved = ResolveResult(name="not-a-real-compound")

    async def fake_aresolve(name: str) -> ResolveResult:
        del name
        return unresolved

    monkeypatch.setattr(dmta_cli, "aresolve", fake_aresolve)

    result = await augment_name("not-a-real-compound")

    assert result.resolved is False
    assert result.smiles is None
    assert result.aliases == []
