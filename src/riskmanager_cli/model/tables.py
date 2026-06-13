"""
SQLModel table definitions for the riskmanager CLI data model.

All 16 tables are defined here using SQLModel (SQLAlchemy + Pydantic integration).
UUIDs are stored as TEXT, timestamps as DATETIME (UTC ISO 8601), and enums as
TEXT via ``SAEnum(MyEnum, native_enum=False)``.

Why this exists:
    The reference implementation imports models from the ``riskmanager_server``
    wheel. In this greenfield application all models are re-implemented locally
    so that the package has zero external wheel dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel
from typing_extensions import Self

from .enums import TA, NcrmRole

# ---------------------------------------------------------------------------
# CRUDMixin — replaces the riskmanager_server wheel's base class
# ---------------------------------------------------------------------------


class CRUDMixin:
    """Generic CRUD helpers for all SQLModel table classes.

    Provides ``get_all``, ``get_where``, and ``update_fields`` as class/instance
    methods so that each model class avoids boilerplate query code.

    Why this exists:
        The reference implementation inherits these from ``CRUDBase`` in the
        ``riskmanager_server`` wheel. Implementing locally removes the external
        dependency while preserving the identical API used throughout the
        operations layer.
    """

    @classmethod
    async def get_all(cls, session: AsyncSession) -> list[Self]:
        """Fetch all records of this model type.

        Args:
            session: An open :class:`~sqlalchemy.ext.asyncio.AsyncSession`.

        Returns:
            A list of all model instances, or an empty list if none exist.
        """
        result = await session.execute(select(cls))
        return list(result.scalars().all())

    @classmethod
    async def get_where(cls, session: AsyncSession, condition: Any) -> list[Self]:
        """Fetch records matching a SQLAlchemy filter condition.

        Args:
            session: An open :class:`~sqlalchemy.ext.asyncio.AsyncSession`.
            condition: A SQLAlchemy column expression (e.g. ``Model.id == value``).
                Typed as ``Any`` because SQLModel's instrumented attribute ``__eq__``
                returns ``ColumnElement[bool]`` at runtime, but mypy infers ``bool``
                from the underlying Python ``object.__eq__`` — a known gap in
                SQLModel/SQLAlchemy's mypy stubs.

        Returns:
            A list of matching model instances, or an empty list.
        """
        result = await session.execute(select(cls).where(condition))
        return list(result.scalars().all())

    async def update_fields(self, session: AsyncSession, **kwargs: Any) -> None:
        """Update specified fields on this instance and commit.

        Args:
            session: An open :class:`~sqlalchemy.ext.asyncio.AsyncSession`.
            **kwargs: Field names and their new values.
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        session.add(self)
        await session.commit()
        await session.refresh(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> str:
    """Generate a new UUID4 string primary key."""
    return str(uuid4())


def _now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Core entity tables
# ---------------------------------------------------------------------------


class Material(SQLModel, CRUDMixin, table=True):
    """Central entity representing a chemical substance.

    Attributes:
        id: UUID primary key (TEXT in SQLite).
        name: Human-readable name; unique across all materials.
        display_name: Short label shown in listings; required, not unique
            (defaults to ``name`` when not supplied).
        interpret_chemically: Whether SMILES is semantically interpreted.
        smiles: Canonical SMILES notation; unique when set.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "material"
    __table_args__ = (
        Index("idx_material_name", "name", unique=True),
        Index("idx_material_smiles", "smiles", unique=True),
    )

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    name: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    display_name: str = Field(sa_column=Column(Text, nullable=False))
    interpret_chemically: bool = Field(
        sa_column=Column(Boolean, nullable=False, default=False)
    )
    smiles: str | None = Field(default=None, sa_column=Column(Text, unique=True))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class MaterialAlias(SQLModel, CRUDMixin, table=True):
    """One alias per row for a material.

    Normalised alias storage replacing the ARRAY column in the reference
    implementation.

    Attributes:
        id: UUID primary key.
        material_id: Foreign key to :class:`Material` (CASCADE delete).
        alias: Alias string.
        created_at: UTC timestamp of record creation.
    """

    __tablename__ = "material_alias"
    __table_args__ = (Index("idx_material_alias_material_id", "material_id"),)

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    material_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("material.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    alias: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class Project(SQLModel, CRUDMixin, table=True):
    """A project linking a material to a therapy area.

    Contains one or more :class:`ManufacturingProcess` records.

    Attributes:
        id: UUID primary key.
        name: Project name.
        therapy_area: Therapy area classification; see :class:`~.enums.TA`.
        material_id: Foreign key to :class:`Material` (RESTRICT delete).
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "project"
    __table_args__ = (Index("idx_project_material_id", "material_id"),)

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    name: str = Field(sa_column=Column(Text, nullable=False))
    therapy_area: TA = Field(sa_column=Column(SAEnum(TA, native_enum=False), nullable=False))
    material_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("material.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class ManufacturingProcess(SQLModel, CRUDMixin, table=True):
    """A specific route and process combination within a project.

    Identified by the tuple ``(project_id, route_number, process_number)``,
    which is enforced as a unique constraint.

    Attributes:
        id: UUID primary key.
        project_id: Foreign key to :class:`Project` (RESTRICT delete).
        route_number: Route identifier within the project.
        process_number: Process identifier within the route.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "manufacturing_processes"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "route_number",
            "process_number",
            name="uq_project_mfg_process",
        ),
        Index("idx_mfg_process_project", "project_id"),
    )

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    project_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("project.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    route_number: int = Field(sa_column=Column(Integer, nullable=False))
    process_number: int = Field(sa_column=Column(Integer, nullable=False))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class ManufacturingProcessRisk(SQLModel, CRUDMixin, table=True):
    """Risk assessment at the manufacturing process level.

    Attributes:
        id: UUID primary key.
        manufacturing_process_id: FK to :class:`ManufacturingProcess` (CASCADE).
        risk_type: Category of risk (e.g. 'Safety', 'Quality', 'Supply').
        name: Short title of the risk.
        description: Optional detailed description.
        current_level: Current risk score (1–5; 5 = Critical).
        proposed_mitigation: Proposed action to reduce risk.
        mitigated_level: Projected risk score after mitigation.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "manufacturing_process_risk"
    __table_args__ = (
        Index(
            "idx_mfg_process_risk_process_id",
            "manufacturing_process_id",
        ),
    )

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    manufacturing_process_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("manufacturing_processes.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    risk_type: str = Field(sa_column=Column(Text, nullable=False))
    name: str = Field(sa_column=Column(Text, nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text))
    current_level: int | None = Field(default=None, sa_column=Column(Integer))
    proposed_mitigation: str | None = Field(default=None, sa_column=Column(Text))
    mitigated_level: int | None = Field(default=None, sa_column=Column(Integer))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class Component(SQLModel, CRUDMixin, table=True):
    """A material in the context of a manufacturing process.

    Defines the component's role in the overall process. Per-stage linkage is
    handled by :class:`StageComponent`.

    Attributes:
        id: UUID primary key.
        process_id: FK to :class:`ManufacturingProcess` (RESTRICT delete).
        material_id: FK to :class:`Material` (RESTRICT delete).
        control_strategy_role: Optional role label ('API', 'CRUDE', 'RSM', etc.).
        is_isolated: Whether the component is isolated in this process.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "component"
    __table_args__ = (
        Index("idx_component_mfg_process", "process_id"),
        Index("idx_component_material", "material_id"),
    )

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    process_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("manufacturing_processes.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    material_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("material.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    control_strategy_role: str | None = Field(default=None, sa_column=Column(Text))
    is_isolated: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, default=True),
    )
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class ComponentRisk(SQLModel, CRUDMixin, table=True):
    """Risk assessment for a specific component.

    Attributes:
        id: UUID primary key.
        component_id: FK to :class:`Component` (CASCADE delete).
        risk_type: Category of risk.
        name: Short title of the risk.
        description: Optional detailed description.
        current_level: Current risk score.
        proposed_mitigation: Proposed mitigation action.
        mitigated_level: Post-mitigation risk score.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "component_risk"
    __table_args__ = (Index("idx_component_risk_component_id", "component_id"),)

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    component_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("component.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    risk_type: str = Field(sa_column=Column(Text, nullable=False))
    name: str = Field(sa_column=Column(Text, nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text))
    current_level: int | None = Field(default=None, sa_column=Column(Integer))
    proposed_mitigation: str | None = Field(default=None, sa_column=Column(Text))
    mitigated_level: int | None = Field(default=None, sa_column=Column(Integer))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class Counterion(SQLModel, CRUDMixin, table=True):
    """Charged chemical species used in salt formation.

    Attributes:
        id: UUID primary key.
        name: Counterion name (e.g. 'Chloride'); unique.
        display_name: Short label shown in listings; required, not unique
            (defaults to ``name`` when not supplied).
        interpret_chemically: Whether SMILES is semantically interpreted.
        smiles: Optional canonical SMILES notation; unique when set.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "counterion"

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    name: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    display_name: str = Field(sa_column=Column(Text, nullable=False))
    interpret_chemically: bool = Field(
        sa_column=Column(Boolean, nullable=False, default=False)
    )
    smiles: str | None = Field(default=None, sa_column=Column(Text, unique=True))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class CounterionAlias(SQLModel, CRUDMixin, table=True):
    """One alias per row for a counterion.

    Attributes:
        id: UUID primary key.
        counterion_id: FK to :class:`Counterion` (CASCADE delete).
        alias: Alias string.
        created_at: UTC timestamp of record creation.
    """

    __tablename__ = "counterion_alias"
    __table_args__ = (Index("idx_counterion_alias_counterion_id", "counterion_id"),)

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    counterion_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("counterion.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    alias: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class ComponentSalt(SQLModel, CRUDMixin, table=True):
    """Salt formation data linking a component to a counterion.

    Attributes:
        id: UUID primary key.
        component_id: FK to :class:`Component` (CASCADE delete).
        counterion_id: FK to :class:`Counterion` (RESTRICT delete).
        stoichiometry: Salt stoichiometry ratio (e.g. 1.0, 0.5).
        is_fully_defined: Whether the salt form is fully defined.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "component_salt"
    __table_args__ = (Index("idx_component_salt_component_id", "component_id"),)

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    component_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("component.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    counterion_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("counterion.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    stoichiometry: float | None = Field(
        default=None,
        sa_column=Column(Numeric(precision=5, scale=2), nullable=True),
    )
    is_fully_defined: bool | None = Field(default=None, sa_column=Column(Boolean, nullable=True))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class Stage(SQLModel, CRUDMixin, table=True):
    """A discrete manufacturing step within a process.

    Examples: Reaction, Purification, Isolation, Crystallisation.

    Attributes:
        id: UUID primary key.
        process_id: FK to :class:`ManufacturingProcess` (RESTRICT delete).
        name: Stage name.
        number: Stage sequence number within the process; unique per process.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "stage"
    __table_args__ = (
        UniqueConstraint(
            "process_id",
            "number",
            name="uq_stage_number_per_mfg_process",
        ),
        Index("idx_stage_mfg_process", "process_id"),
    )

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    process_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("manufacturing_processes.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    name: str = Field(sa_column=Column(Text, nullable=False))
    number: int = Field(sa_column=Column(Integer, nullable=False))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class StageRisk(SQLModel, CRUDMixin, table=True):
    """Risk assessment at the stage level.

    Attributes:
        id: UUID primary key.
        stage_id: FK to :class:`Stage` (CASCADE delete).
        risk_type: Category of risk (e.g. 'risk', 'ipc').
        name: Short title of the risk.
        description: Optional detailed description.
        current_level: Current risk score.
        proposed_mitigation: Proposed mitigation action.
        mitigated_level: Post-mitigation risk score.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "stage_risk"
    __table_args__ = (Index("idx_stage_risk_stage_id", "stage_id"),)

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    stage_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("stage.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    risk_type: str = Field(sa_column=Column(Text, nullable=False))
    name: str = Field(sa_column=Column(Text, nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text))
    current_level: int | None = Field(default=None, sa_column=Column(Integer))
    proposed_mitigation: str | None = Field(default=None, sa_column=Column(Text))
    mitigated_level: int | None = Field(default=None, sa_column=Column(Integer))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class StageComponent(SQLModel, CRUDMixin, table=True):
    """Junction table linking a stage to a component.

    A component may appear in multiple stages. ``component_type`` indicates
    whether the component is a ``'reactant'`` or a ``'product'`` in this stage.

    Attributes:
        id: UUID primary key.
        stage_id: FK to :class:`Stage` (CASCADE delete).
        component_id: FK to :class:`Component` (RESTRICT delete).
        component_type: ``'reactant'`` or ``'product'``; validated by Pydantic.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "stage_components"
    __table_args__ = (
        UniqueConstraint("stage_id", "component_id", name="uq_stage_component"),
        Index("idx_stage_components_stage", "stage_id"),
        Index("idx_stage_components_component", "component_id"),
        Index("idx_stage_components_type", "component_type"),
    )

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    stage_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("stage.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    component_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("component.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    component_type: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class NcrmLibrary(SQLModel, CRUDMixin, table=True):
    """Non-controlled raw materials library entry.

    Covers solvents, reagents, catalysts, additives, and internal standards.

    Attributes:
        id: UUID primary key.
        display_name: Short label shown in listings; required, not unique
            (defaults to ``name`` when not supplied).
        name: Common chemical name; unique.
        interpret_chemically: Whether SMILES is semantically interpreted.
        smiles: Optional canonical SMILES notation.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "ncrm_library"

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    display_name: str = Field(sa_column=Column(Text, nullable=False))
    name: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    interpret_chemically: bool = Field(sa_column=Column(Boolean, nullable=False, default=False))
    smiles: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class NcrmLibraryAlias(SQLModel, CRUDMixin, table=True):
    """One alias per row for an NCRM library entry.

    Attributes:
        id: UUID primary key.
        ncrm_library_id: FK to :class:`NcrmLibrary` (CASCADE delete).
        alias: Alias string.
        created_at: UTC timestamp of record creation.
    """

    __tablename__ = "ncrm_library_alias"
    __table_args__ = (Index("idx_ncrm_library_alias_ncrm_id", "ncrm_library_id"),)

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    ncrm_library_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("ncrm_library.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    alias: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )


class StageNcrm(SQLModel, CRUDMixin, table=True):
    """Junction table linking a stage to an NCRM library entry with its role.

    Attributes:
        id: UUID primary key.
        ncrm_id: FK to :class:`NcrmLibrary` (RESTRICT delete).
        stage_id: FK to :class:`Stage` (RESTRICT delete).
        role: NCRM role; see :class:`~.enums.NcrmRole`.
        created_at: UTC timestamp of record creation.
        updated_at: UTC timestamp of most recent modification.
    """

    __tablename__ = "stage_ncrms"

    id: str | None = Field(
        default_factory=_uuid,
        sa_column=Column(Text, primary_key=True),
    )
    ncrm_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("ncrm_library.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    stage_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("stage.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    role: NcrmRole = Field(sa_column=Column(SAEnum(NcrmRole, native_enum=False), nullable=False))
    created_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime | None = Field(
        default_factory=_now,
        sa_column=Column(DateTime, nullable=False),
    )
