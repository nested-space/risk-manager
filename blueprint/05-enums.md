# Enumerations

## Overview

Two active enumerations are used in the greenfield application. Both are defined
as Python `enum.Enum` subclasses and stored as `TEXT` in SQLite via SQLAlchemy's
`Enum` type with `native_enum=False`.

**No database-level `CHECK` constraints** are applied. Pydantic schemas validate
enum values at the application boundary (create and update operations). This
preserves flexibility during development — new values can be used in the database
before the Python code is updated.

---

## `TA` — Therapy Area

Used by: `project.therapy_area`

```python
from enum import Enum

class TA(str, Enum):
    """Therapy area classification for projects."""
    ONCOLOGY = "Oncology"
    CVRM = "CVRM"
    RESPIRATORY_AND_IMMUNOLOGY = "Respiratory and Immunology"
    VACCINES_AND_IMMUNE_THERAPIES = "Vaccines and Immune Therapies"
    RARE_DISEASES = "Rare Diseases"
```

| Enum Member | Stored Value |
|-------------|-------------|
| `TA.ONCOLOGY` | `"Oncology"` |
| `TA.CVRM` | `"CVRM"` |
| `TA.RESPIRATORY_AND_IMMUNOLOGY` | `"Respiratory and Immunology"` |
| `TA.VACCINES_AND_IMMUNE_THERAPIES` | `"Vaccines and Immune Therapies"` |
| `TA.RARE_DISEASES` | `"Rare Diseases"` |

**REPL command values (exact strings, case-sensitive):**
```
/add project --therapy-area "Oncology"
/add project --therapy-area "CVRM"
/add project --therapy-area "Respiratory and Immunology"
/add project --therapy-area "Vaccines and Immune Therapies"
/add project --therapy-area "Rare Diseases"
```

During guided prompts, the REPL will present these as numbered choices.

---

## `NcrmRole` — NCRM Role

Used by: `stage_ncrms.role`

```python
from enum import Enum

class NcrmRole(str, Enum):
    """Role of a non-controlled raw material within a stage."""
    REAGENT = "reagent"
    CATALYST = "catalyst"
    SOLVENT = "solvent"
    ADDITIVE = "additive"
    INTERNAL_STANDARD = "internal_standard"
```

| Enum Member | Stored Value | Description |
|-------------|-------------|-------------|
| `NcrmRole.REAGENT` | `"reagent"` | Chemical that participates in the reaction |
| `NcrmRole.CATALYST` | `"catalyst"` | Promotes reaction without being consumed |
| `NcrmRole.SOLVENT` | `"solvent"` | Reaction medium |
| `NcrmRole.ADDITIVE` | `"additive"` | Supporting additive (base, acid, etc.) |
| `NcrmRole.INTERNAL_STANDARD` | `"internal_standard"` | Reference compound for analysis |

**REPL commands (valid role values):**

```
/add stage-ncrm    (then prompted for role: reagent / catalyst / solvent / additive / internal_standard)
/add ncrm <name> --role reagent
/add ncrm <name> --role catalyst
/add ncrm <name> --role solvent
/add ncrm <name> --role additive
/add ncrm <name> --role internal_standard
```

---

## Excluded Enumerations

The following enums from the reference implementation are **not included** because
their associated tables (`project_status`, `interaction`) are excluded:

| Enum | Reason Excluded |
|------|----------------|
| `CDPPhase` | Used only by `project_status.cdp_phase` |
| `ClinicalPhase` | Used only by `project_status.clinical_phase` |
| `Status` | Used only by `interaction.status` |

---

## SQLAlchemy Model Usage

```python
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field
from .enums import TA, NcrmRole

class Project(SQLModel, table=True):
    __tablename__ = "project"

    therapy_area: TA = Field(
        sa_column=Column(
            SAEnum(TA, native_enum=False),  # stored as TEXT, no DB enum type
            nullable=False,
        )
    )
```

---

## Pydantic Schema Validation

```python
from pydantic import BaseModel
from .enums import TA

class ProjectCreate(BaseModel):
    name: str
    therapy_area: TA         # Pydantic validates: must be a valid TA member
    material_id: UUID

# Usage:
data = ProjectCreate(name="Alpha", therapy_area="Oncology", material_id=some_uuid)
# Pydantic coerces the string "Oncology" to TA.ONCOLOGY automatically (str enum)

# Invalid value raises ValidationError at the Python layer:
data = ProjectCreate(name="Alpha", therapy_area="Invalid", material_id=some_uuid)
# → pydantic.ValidationError: 'therapy_area' is not a valid TA
```
