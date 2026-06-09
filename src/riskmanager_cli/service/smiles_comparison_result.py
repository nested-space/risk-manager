"""DMTA SMILES lookup result dataclass.

:class:`SmilesComparisonResult` carries the compound data returned by the DMTA
API for a single matched compound.  All fields are optional so that partial
records (API returning only a subset of fields) are handled gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SmilesComparisonResult:
    """Result of a DMTA compound-registry lookup.

    Attributes:
        smiles: Canonical SMILES string for the compound, or ``None`` when the
            registry does not hold a structure.
        name: IUPAC or preferred name as held by the registry.
        formula: Molecular formula (e.g. ``"C6H12O6"``).
        molecular_weight: Molecular weight in g/mol.
        registry_id: Internal DMTA compound identifier.
        extra: Any additional key/value pairs returned by the API that do not
            correspond to a declared field.
    """

    smiles: str | None = None
    name: str | None = None
    formula: str | None = None
    molecular_weight: float | None = None
    registry_id: str | None = None
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, payload: dict[str, object]) -> SmilesComparisonResult:
        """Construct a :class:`SmilesComparisonResult` from a raw API payload.

        Unknown keys are collected into :attr:`extra` rather than discarded so
        that callers can inspect unexpected fields without crashing.

        Args:
            payload: Deserialised JSON object returned by the DMTA API.

        Returns:
            A populated :class:`SmilesComparisonResult` instance.
        """
        known_keys = {"smiles", "name", "formula", "molecular_weight", "registry_id"}
        mw_raw = payload.get("molecular_weight")
        mw: float | None = float(mw_raw) if mw_raw is not None else None  # type: ignore[arg-type]
        return cls(
            smiles=str(payload["smiles"]) if "smiles" in payload else None,
            name=str(payload["name"]) if "name" in payload else None,
            formula=str(payload["formula"]) if "formula" in payload else None,
            molecular_weight=mw,
            registry_id=str(payload["registry_id"]) if "registry_id" in payload else None,
            extra={k: v for k, v in payload.items() if k not in known_keys},
        )
