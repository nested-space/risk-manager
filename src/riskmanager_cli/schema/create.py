"""
Pydantic create schemas for all riskmanager CLI entities.

Each schema defines the required and optional fields that a caller must supply
when creating a new database record. Pydantic validates types and enum values
at the application boundary before any database interaction.

Why this exists:
    Separating create/update contracts from SQLModel table definitions keeps
    the ORM layer focused on persistence and the schema layer focused on
    input validation. This matches the pattern used in the reference
    implementation's ``riskmanager_server`` wheel.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from ..model.enums import TA, NcrmRole


class MaterialCreate(BaseModel):
    """Fields required to create a new :class:`~..model.tables.Material`.

    Attributes:
        name: Human-readable material name; must be unique.
        smiles: Optional canonical SMILES notation.
    """

    name: str
    smiles: str | None = None


class MaterialAliasCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.MaterialAlias`.

    Attributes:
        material_id: UUID of the parent material.
        alias: Alias string to associate with the material.
    """

    material_id: UUID
    alias: str


class ProjectCreate(BaseModel):
    """Fields required to create a new :class:`~..model.tables.Project`.

    Attributes:
        name: Project name.
        therapy_area: Therapy area classification; must be a valid :class:`~..model.enums.TA`.
        material_id: UUID of the associated material.
    """

    name: str
    therapy_area: TA
    material_id: UUID


class ManufacturingProcessCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.ManufacturingProcess`.

    Attributes:
        project_id: UUID of the parent project.
        route_number: Route identifier within the project.
        process_number: Process identifier within the route.
    """

    project_id: UUID
    route_number: int = Field(ge=1)
    process_number: int = Field(ge=1)


class ManufacturingProcessRiskCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.ManufacturingProcessRisk`.

    Attributes:
        manufacturing_process_id: UUID of the parent manufacturing process.
        risk_type: Category of risk (e.g. 'Safety', 'Quality', 'Supply').
        name: Short title of the risk.
        description: Optional detailed description.
        current_level: Current risk score (1–10 typical).
        proposed_mitigation: Proposed action to reduce risk.
        mitigated_level: Projected risk score after mitigation.
    """

    manufacturing_process_id: UUID
    risk_type: str
    name: str
    description: str | None = None
    current_level: int | None = Field(default=None, ge=1, le=10)
    proposed_mitigation: str | None = None
    mitigated_level: int | None = Field(default=None, ge=1, le=10)


class ComponentCreate(BaseModel):
    """Fields required to create a new :class:`~..model.tables.Component`.

    Attributes:
        process_id: UUID of the parent manufacturing process.
        material_id: UUID of the associated material.
        control_strategy_role: Optional role label ('API', 'CRUDE', 'RSM', etc.).
        is_isolated: Whether the component is isolated in this process.
    """

    process_id: UUID
    material_id: UUID
    control_strategy_role: str | None = None
    is_isolated: bool = False


class ComponentRiskCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.ComponentRisk`.

    Attributes:
        component_id: UUID of the parent component.
        risk_type: Category of risk.
        name: Short title of the risk.
        description: Optional detailed description.
        current_level: Current risk score (1–10 typical).
        proposed_mitigation: Proposed mitigation action.
        mitigated_level: Post-mitigation risk score.
    """

    component_id: UUID
    risk_type: str
    name: str
    description: str | None = None
    current_level: int | None = Field(default=None, ge=1, le=10)
    proposed_mitigation: str | None = None
    mitigated_level: int | None = Field(default=None, ge=1, le=10)


class CounterionCreate(BaseModel):
    """Fields required to create a new :class:`~..model.tables.Counterion`.

    Attributes:
        name: Counterion name (e.g. 'Chloride'); must be unique.
        smiles: Optional canonical SMILES notation.
    """

    name: str
    smiles: str | None = None


class CounterionAliasCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.CounterionAlias`.

    Attributes:
        counterion_id: UUID of the parent counterion.
        alias: Alias string.
    """

    counterion_id: UUID
    alias: str


class ComponentSaltCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.ComponentSalt`.

    Attributes:
        component_id: UUID of the parent component.
        counterion_id: UUID of the associated counterion.
        stoichiometry: Optional stoichiometry ratio (e.g. 1.0, 0.5).
        is_fully_defined: Whether the salt form is fully defined.
    """

    component_id: UUID
    counterion_id: UUID
    stoichiometry: float | None = None
    is_fully_defined: bool | None = None


class StageCreate(BaseModel):
    """Fields required to create a new :class:`~..model.tables.Stage`.

    Attributes:
        process_id: UUID of the parent manufacturing process.
        name: Stage name.
        number: Stage sequence number within the process; must be unique per process.
    """

    process_id: UUID
    name: str
    number: int = Field(ge=1)


class StageRiskCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.StageRisk`.

    Attributes:
        stage_id: UUID of the parent stage.
        risk_type: Category of risk (e.g. 'risk', 'ipc').
        name: Short title of the risk.
        description: Optional detailed description.
        current_level: Current risk score (1–10 typical).
        proposed_mitigation: Proposed mitigation action.
        mitigated_level: Post-mitigation risk score.
    """

    stage_id: UUID
    risk_type: str
    name: str
    description: str | None = None
    current_level: int | None = Field(default=None, ge=1, le=10)
    proposed_mitigation: str | None = None
    mitigated_level: int | None = Field(default=None, ge=1, le=10)


class StageComponentCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.StageComponent`.

    Attributes:
        stage_id: UUID of the parent stage.
        component_id: UUID of the component to link.
        component_type: ``'reactant'`` or ``'product'``.
    """

    stage_id: UUID
    component_id: UUID
    component_type: str = Field(pattern="^(reactant|product)$")


class NcrmLibraryCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.NcrmLibrary` entry.

    Attributes:
        display_name: Primary display name; must be unique.
        common_name: Common chemical name; must be unique.
        interpret_chemically: Whether SMILES is semantically interpreted.
        smiles: Optional canonical SMILES notation.
    """

    display_name: str
    common_name: str
    interpret_chemically: bool = False
    smiles: str | None = None


class NcrmLibraryAliasCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.NcrmLibraryAlias`.

    Attributes:
        ncrm_library_id: UUID of the parent NCRM library entry.
        alias: Alias string.
    """

    ncrm_library_id: UUID
    alias: str


class StageNcrmCreate(BaseModel):
    """Fields required to create a :class:`~..model.tables.StageNcrm`.

    Attributes:
        ncrm_id: UUID of the NCRM library entry.
        stage_id: UUID of the stage.
        role: NCRM role; must be a valid :class:`~..model.enums.NcrmRole`.
    """

    ncrm_id: UUID
    stage_id: UUID
    role: NcrmRole
