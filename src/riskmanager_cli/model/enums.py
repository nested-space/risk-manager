"""
Enumeration types for the riskmanager CLI data model.

Defines all Python ``enum.Enum`` subclasses used by SQLModel table definitions
and Pydantic schema validators. SQLite stores enum values as ``TEXT`` via
``SAEnum(MyEnum, native_enum=False)``; no database-level CHECK constraints are
applied. Pydantic schemas enforce valid values at the application boundary.

Why this exists:
    Centralises all domain-specific enumerated values so that both the ORM
    layer (``model/tables.py``) and the schema layer (``schema/``) import from
    a single source of truth.
"""

from enum import Enum


class TA(str, Enum):
    """Therapy area classification for projects.

    Values are stored as their string representations in SQLite.

    Attributes:
        ONCOLOGY: Oncology therapy area.
        CVRM: Cardiovascular, Renal and Metabolism therapy area.
        RESPIRATORY_AND_IMMUNOLOGY: Respiratory and Immunology therapy area.
        VACCINES_AND_IMMUNE_THERAPIES: Vaccines and Immune Therapies.
        RARE_DISEASES: Rare Diseases therapy area.
    """

    ONCOLOGY = "Oncology"
    CVRM = "CVRM"
    RESPIRATORY_AND_IMMUNOLOGY = "Respiratory and Immunology"
    VACCINES_AND_IMMUNE_THERAPIES = "Vaccines and Immune Therapies"
    RARE_DISEASES = "Rare Diseases"


class NcrmRole(str, Enum):
    """Role of a non-controlled raw material within a manufacturing stage.

    Values are stored as their string representations in SQLite.

    Attributes:
        REAGENT: Chemical that participates in the reaction.
        CATALYST: Promotes the reaction without being consumed.
        SOLVENT: Reaction medium.
        ADDITIVE: Supporting additive (base, acid, etc.).
        INTERNAL_STANDARD: Reference compound for analysis.
    """

    REAGENT = "reagent"
    CATALYST = "catalyst"
    SOLVENT = "solvent"
    ADDITIVE = "additive"
    INTERNAL_STANDARD = "internal_standard"
