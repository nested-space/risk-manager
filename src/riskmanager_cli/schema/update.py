"""
Pydantic update schemas for all riskmanager CLI entities.

Each schema defines fields that may be updated on an existing record. All
fields are optional — callers supply only the fields they wish to change.
A ``None`` value means "do not change this field".

Why this exists:
    Update contracts differ from create contracts: no field is required (the
    record already exists), and some fields (e.g. primary keys, immutable
    foreign keys) are intentionally excluded. Keeping these schemas separate
    from create schemas prevents accidental partial-update misuse.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from ..model.enums import TA, NcrmRole


class MaterialUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.Material`.

    Attributes:
        name: New human-readable name.
        display_name: New short label.
        interpret_chemically: Update chemical interpretation flag.
        smiles: New canonical SMILES notation; pass ``""`` to clear.
    """

    name: str | None = None
    display_name: str | None = None
    interpret_chemically: bool | None = None
    smiles: str | None = None


class ProjectUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.Project`.

    Attributes:
        name: New project name.
        therapy_area: New therapy area classification.
        material_id: Reassign to a different material UUID.
    """

    name: str | None = None
    therapy_area: TA | None = None
    material_id: UUID | None = None


class ManufacturingProcessUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.ManufacturingProcess`.

    Attributes:
        route_number: New route identifier.
        process_number: New process identifier.
    """

    route_number: int | None = Field(default=None, ge=1)
    process_number: int | None = Field(default=None, ge=1)


class ManufacturingProcessRiskUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.ManufacturingProcessRisk`.

    Attributes:
        risk_type: New risk category.
        name: New short title.
        description: New or updated description.
        current_level: New current risk score.
        proposed_mitigation: New proposed mitigation.
        mitigated_level: New post-mitigation risk score.
    """

    risk_type: str | None = None
    name: str | None = None
    description: str | None = None
    current_level: int | None = Field(default=None, ge=1, le=5)
    proposed_mitigation: str | None = None
    mitigated_level: int | None = Field(default=None, ge=1, le=5)


class ComponentUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.Component`.

    Attributes:
        control_strategy_role: New role label.
        is_isolated: Update isolation status.
    """

    control_strategy_role: str | None = None
    is_isolated: bool | None = None


class ComponentRiskUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.ComponentRisk`.

    Attributes:
        risk_type: New risk category.
        name: New short title.
        description: New or updated description.
        current_level: New current risk score.
        proposed_mitigation: New proposed mitigation.
        mitigated_level: New post-mitigation risk score.
    """

    risk_type: str | None = None
    name: str | None = None
    description: str | None = None
    current_level: int | None = Field(default=None, ge=1, le=5)
    proposed_mitigation: str | None = None
    mitigated_level: int | None = Field(default=None, ge=1, le=5)


class CounterionUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.Counterion`.

    Attributes:
        name: New counterion name.
        display_name: New short label.
        interpret_chemically: Update chemical interpretation flag.
        smiles: New canonical SMILES notation.
    """

    name: str | None = None
    display_name: str | None = None
    interpret_chemically: bool | None = None
    smiles: str | None = None


class ComponentSaltUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.ComponentSalt`.

    Attributes:
        stoichiometry: New stoichiometry ratio.
        is_fully_defined: Update whether the salt form is fully defined.
    """

    stoichiometry: float | None = None
    is_fully_defined: bool | None = None


class StageUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.Stage`.

    Attributes:
        name: New stage name.
        number: New sequence number; must remain unique within the process.
    """

    name: str | None = None
    number: int | None = Field(default=None, ge=1)


class StageRiskUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.StageRisk`.

    Attributes:
        risk_type: New risk category.
        name: New short title.
        description: New or updated description.
        current_level: New current risk score.
        proposed_mitigation: New proposed mitigation.
        mitigated_level: New post-mitigation risk score.
    """

    risk_type: str | None = None
    name: str | None = None
    description: str | None = None
    current_level: int | None = Field(default=None, ge=1, le=5)
    proposed_mitigation: str | None = None
    mitigated_level: int | None = Field(default=None, ge=1, le=5)


class StageComponentUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.StageComponent`.

    Attributes:
        component_type: New component type (``'reactant'`` or ``'product'``).
    """

    component_type: str | None = Field(default=None, pattern="^(reactant|product)$")


class NcrmLibraryUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.NcrmLibrary` entry.

    Attributes:
        display_name: New short label.
        name: New common chemical name.
        interpret_chemically: Update chemical interpretation flag.
        smiles: New canonical SMILES notation.
    """

    display_name: str | None = None
    name: str | None = None
    interpret_chemically: bool | None = None
    smiles: str | None = None


class StageNcrmUpdate(BaseModel):
    """Updatable fields on a :class:`~..model.tables.StageNcrm`.

    Attributes:
        role: New NCRM role classification.
    """

    role: NcrmRole | None = None
