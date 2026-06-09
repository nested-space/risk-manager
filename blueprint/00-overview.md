# Governance CLI — Blueprint Overview

## Purpose

This blueprint describes the complete specification for a **greenfield, single-user,
self-sufficient Python interactive REPL application** for managing pharmaceutical
manufacturing governance data. It is derived from the `governance-cli` reference
implementation but redesigned as a **persistent, full-screen interactive shell**
using `blessed` for terminal control, adapted to use **SQLite** (not PostgreSQL),
and contains **no dependency** on the `governance_server` wheel.

The output of this blueprint is a standalone application a developer can build
from scratch, covering the interactive REPL layer, business logic layer, and
persistence layer.

### Key Design Philosophy: Context-Aware Navigation

Unlike a traditional single-shot CLI (where every command must supply its full
context), this application maintains a **persistent session context**. The user
navigates a hierarchy of entities (Project → Route → Stage/Component) using
slash-commands and arrow-key list selection. Once a project and route are
selected, subsequent commands operate within that context without re-specifying
the full path.

**Entry point:** `gcli` launches the interactive REPL shell directly.

---

## What This Application Does

The application provides command-line management of structured pharmaceutical data
across the following entity hierarchy:

```
Material
  └── Project
        └── ManufacturingProcess
              ├── ManufacturingProcessRisk
              ├── Stage
              │     ├── StageRisk
              │     ├── StageComponent → Component
              │     └── StageNcrm → NcrmLibrary
              └── Component
                    ├── ComponentRisk
                    └── ComponentSalt → Counterion
```

### Core Entities

| Entity | Description |
|--------|-------------|
| **Material** | Chemical substance with optional SMILES notation; central entity |
| **Project** | Groups manufacturing routes for a material under a therapy area |
| **ManufacturingProcess** | A specific route+process combination within a project |
| **ManufacturingProcessRisk** | Risk assessments at the manufacturing process level |
| **Stage** | A discrete step within a manufacturing process (reaction, purification, etc.) |
| **StageRisk** | Risk assessments at the stage level |
| **StageComponent** | Link between a stage and a component (reactant or product) |
| **Component** | A material used in a manufacturing process with its role |
| **ComponentRisk** | Risk assessments for a specific component |
| **ComponentSalt** | Salt formation data linking a component to a counterion |
| **NcrmLibrary** | Non-controlled raw materials (solvents, reagents, catalysts, etc.) |
| **StageNcrm** | Link between a stage and an NCRM with its role |
| **Counterion** | Charged species used in salt formation |

---

## Scope: What Is Included

- **Interactive REPL layer** — `blessed`-based full-screen shell; slash-command grammar; arrow-key list navigation; context-aware screen management
- **Business logic layer** — operations, SMILES validation, DMTA enrichment
- **Persistence layer** — SQLite via SQLAlchemy async + aiosqlite
- **Session state** — JSON-backed recents/context memory at `~/.gcli/session.json`
- **All entities listed above**
- **SMILES canonicalization and analysis tools** (requires RDKit)
- **Bulk CSV import** via `/admin import` commands within the REPL
- **Dry-run mode** for destructive operations (as a slash-command flag)
- **Colored terminal output** via colorama
- **Optional DMTA enrichment** for materials (external HTTP service)

## Scope: What Is Excluded

The following from the reference implementation are **not included** in the greenfield:

| Excluded | Reason |
|----------|--------|
| `project_status` table | Governance workflow feature; not needed for single-user app |
| `interaction` (governance_interaction) table | Governance workflow feature; not needed |
| All `*_version` audit tables | Require database triggers; not appropriate for SQLite single-user |
| `governance_server` wheel | All models, schemas, and CRUD helpers are re-implemented locally |
| PostgreSQL / asyncpg | Replaced by SQLite / aiosqlite |
| FastAPI / HTTP server | Not needed; REPL-only application |
| `argparse` / `argcomplete` | Replaced by the interactive REPL command dispatcher |
| Single-shot CLI commands | Replaced by persistent context navigation |

---

## Key Design Decisions

### 1. SQLite Instead of PostgreSQL
The application is designed for single-user local use. SQLite provides zero-configuration,
file-based persistence with no server process required.

### 2. No Audit/Version Tables
The reference implementation maintains `*_version` tables populated by PostgreSQL
triggers. These are omitted here. If audit history is later required, Alembic
migrations or application-level snapshots can be added.

### 3. Alias Sub-tables (Not JSON/ARRAY Columns)
Aliases for `Material`, `NcrmLibrary`, and `Counterion` are stored in normalized
sub-tables (`material_alias`, `ncrm_library_alias`, `counterion_alias`) rather than
as JSON or array columns. This follows the same pattern as `ComponentRisk` and
`StageRisk`, and allows efficient per-alias add/remove operations.

### 4. Enums as Python `enum.Enum` (No CHECK Constraints)
Python `enum.Enum` types are used throughout, with SQLAlchemy storing them as `TEXT`
in SQLite. No database-level `CHECK` constraints are applied. Pydantic schemas enforce
valid enum values at the application layer, preserving flexibility during development.

### 5. JSONB Columns Removed
All JSONB columns from the reference implementation are either:
- **Removed**: `component.properties`, `manufacturing_processes.cqas`
- **Replaced with sub-tables**: `manufacturing_processes.risks` → `manufacturing_process_risk`
- **Deferred to future**: `component.methods`, `component.specifications` (not yet implemented)

---

## Application Identity

| Attribute | Value |
|-----------|-------|
| Package name | `governance-cli` |
| Entry points | `gcli`, `governance-cli` |
| Python requirement | `>=3.10` |
| Current version | `0.3.0` (pre-1.0) |
| License | See `LICENSE` |

---

## File Structure (Greenfield Target)

```
src/
└── governance_cli/
    ├── __init__.py
    ├── __main__.py              # Entry point: init blessed terminal, load session, launch REPL
    ├── repl/                    # Interactive REPL shell layer
    │   ├── __init__.py
    │   ├── loop.py              # Main event loop (blessed inkey, key routing)
    │   ├── screen.py            # Screen manager (status bar, output pane, input line)
    │   ├── context.py           # Navigation context state machine + breadcrumb
    │   ├── commands.py          # Slash command parser and dispatcher
    │   ├── session_state.py     # JSON-backed session persistence (~/.gcli/session.json)
    │   ├── escape_handler.py    # Double-escape navigation logic + unsaved-data guard
    │   ├── list_navigator.py    # Arrow-key list widget (Recents + All sections)
    │   └── renderers/           # Output content renderers
    │       ├── __init__.py
    │       ├── project_renderer.py
    │       ├── route_renderer.py
    │       ├── risk_renderer.py
    │       ├── library_renderer.py
    │       └── admin_renderer.py
    ├── operations/              # Business logic (async, unchanged from architecture)
    │   ├── base_operations.py
    │   ├── material_operations.py
    │   ├── project_operations.py
    │   ├── manufacturing_process_operations.py
    │   ├── manufacturing_process_risk_operations.py
    │   ├── stage_operations.py
    │   ├── stage_component_operations.py
    │   ├── stage_risk_operations.py
    │   ├── stage_ncrm_operations.py
    │   ├── component_operations.py
    │   ├── component_risks_operations.py
    │   ├── component_salt_operations.py
    │   ├── ncrm_library_operations.py
    │   ├── counterion_operations.py
    │   ├── smiles_operations.py
    │   ├── dmta_operations.py
    │   └── visualization_operations.py
    ├── model/                   # SQLModel table definitions (replaces governance_server wheel)
    │   ├── __init__.py
    │   ├── tables.py
    │   └── enums.py
    ├── schema/                  # Pydantic create/update contracts
    │   ├── __init__.py
    │   ├── create.py
    │   └── update.py
    ├── database/                # Session management
    │   ├── __init__.py
    │   ├── connection.py
    │   ├── db_session.py
    │   └── exceptions.py
    ├── config/                  # Environment settings
    │   ├── __init__.py
    │   └── settings.py
    ├── service/                 # External service integrations
    │   ├── __init__.py
    │   ├── DmtaService.py
    │   └── SmilesComparisonResult.py
    └── utils/                   # Console formatting and helpers
        ├── __init__.py
        ├── console_formatting.py
        ├── formula_parser.py
        ├── manufacturing_layout_engine.py
        └── parsing.py
tests/
├── conftest.py
├── operations/
├── repl/
└── utils/
pyproject.toml
requirements.txt
README.md
```
