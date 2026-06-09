# governance-cli

**Interactive REPL shell for pharmaceutical manufacturing governance data.**

`governance-cli` (`gcli`) is a full-screen interactive terminal application for
managing structured pharmaceutical manufacturing data: materials, projects,
manufacturing routes, stages, components, risks, and non-controlled raw materials
(NCRMs). It runs entirely locally with no server process required.

> **Status:** pre-1.0 (`0.3.0`). The CLI surface is stable for single-user local
> use. Consumers should pin to an exact version.

---

## Table of Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Virtual Environment Setup](#virtual-environment-setup)
  - [Install the Package](#install-the-package)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Shell Setup](#shell-setup)
- [Database Initialization](#database-initialization)
- [Launching the Application](#launching-the-application)
- [REPL Interface](#repl-interface)
  - [Screen Layout](#screen-layout)
  - [Navigation Model](#navigation-model)
  - [Escape Navigation](#escape-navigation)
- [Command Reference](#command-reference)
  - [Global Commands](#global-commands)
  - [Home Screen](#home-screen)
  - [Project Screen](#project-screen)
  - [Route View](#route-view)
  - [Stage Focus View](#stage-focus-view)
  - [Component Focus View](#component-focus-view)
  - [Risk Mode](#risk-mode)
  - [Library Track](#library-track)
  - [Admin Sub-mode](#admin-sub-mode)
- [Bulk CSV Import](#bulk-csv-import)
  - [CSV Formats](#csv-formats)
- [Guided Prompts](#guided-prompts)
- [Entity Reference](#entity-reference)
  - [Therapy Areas](#therapy-areas)
  - [NCRM Roles](#ncrm-roles)
- [SMILES and Chemistry](#smiles-and-chemistry)
- [DMTA Enrichment](#dmta-enrichment)
- [Session State](#session-state)
- [Development](#development)
  - [Code Quality Gates](#code-quality-gates)
  - [Running Tests](#running-tests)
  - [Project Structure](#project-structure)
- [Versioning](#versioning)
- [Changelog](#changelog)

---

## Overview

`governance-cli` provides command-line management of structured pharmaceutical
data across the following entity hierarchy:

```
Material
  └── Project
        └── ManufacturingProcess (Route + Process number)
              ├── ManufacturingProcessRisk
              ├── Stage
              │     ├── StageRisk
              │     ├── StageComponent → Component
              │     └── StageNcrm → NcrmLibrary
              └── Component
                    ├── ComponentRisk
                    └── ComponentSalt → Counterion
```

Unlike traditional single-shot CLIs, `gcli` maintains a **persistent session
context**. Once a project and route are selected, subsequent commands operate
within that context without re-specifying the full path.

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | `>=3.10` |
| Operating system | Linux / macOS (blessed terminal required) |
| RDKit | `>=2023.3.1` (for SMILES validation) |

> **Note:** The system Python is NOT used. All commands use the project virtual
> environment at `~/.venvs/riskworks`.

---

## Installation

### Virtual Environment Setup

The project uses a dedicated virtual environment at `~/.venvs/riskworks`.
**Never use the system Python.**

```bash
# Create the virtual environment (one-time setup)
python3 -m venv ~/.venvs/riskworks

# Verify the venv Python version
~/.venvs/riskworks/bin/python --version
# Should print Python 3.10 or higher
```

### Install the Package

```bash
# Clone the repository
git clone <repo-url> riskworks
cd riskworks

# Install in editable mode with dev dependencies
~/.venvs/riskworks/bin/pip install -e ".[dev]"

# Or install production dependencies only
~/.venvs/riskworks/bin/pip install -e .
```

---

## Configuration

### Environment Variables

The application reads all configuration from environment variables. No config
files are required — the defaults work out of the box for local development.

#### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `dev` | Active environment. Accepted: `dev`, `prod` |
| `APP_DEV_DB_PATH` | `./governance-dev.db` | SQLite file path for `dev` |
| `APP_PROD_DB_PATH` | `./governance.db` | SQLite file path for `prod` |
| `APP_DB_PATH` | _(none)_ | Overrides both path vars regardless of `APP_ENV` |

**Precedence:**
1. `APP_DB_PATH` (if set) — always used
2. `APP_ENV=prod` → `APP_PROD_DB_PATH`
3. `APP_ENV=dev` (default) → `APP_DEV_DB_PATH`

#### Session State

| Variable | Default | Description |
|----------|---------|-------------|
| `GCLI_SESSION_PATH` | `~/.gcli/session.json` | JSON session state file |

The session state file is created automatically on first run. If missing or
corrupt, the application starts fresh without error.

#### DMTA Enrichment (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `DMTA_API_URL` | _(none)_ | Base URL of the DMTA enrichment service |
| `DMTA_API_KEY` | _(none)_ | API key for the DMTA service |

If `DMTA_API_URL` is not set and DMTA enrichment is requested, the application
prints a warning and skips enrichment rather than failing.

### Shell Setup

Add the following to `~/.zshrc` or `~/.bashrc`:

```bash
# governance-cli environment
export APP_ENV=dev
export APP_DEV_DB_PATH="$HOME/.gcli/governance-dev.db"
export APP_PROD_DB_PATH="$HOME/.gcli/governance.db"

# Optional: custom session state location
# export GCLI_SESSION_PATH="$HOME/.gcli/session.json"

# Optional: DMTA enrichment
# export DMTA_API_URL="https://dmta.example.com/api"
# export DMTA_API_KEY="your-api-key-here"
```

Create the data directory:

```bash
mkdir -p ~/.gcli
```

---

## Database Initialization

The SQLite database is created automatically on first launch. Tables are
created via SQLAlchemy's `create_all()` — no manual schema setup required.

For production deployments using Alembic migrations:

```bash
~/.venvs/riskworks/bin/alembic upgrade head
```

---

## Launching the Application

```bash
# Using the entry point
~/.venvs/riskworks/bin/gcli

# Or after activating the venv
source ~/.venvs/riskworks/bin/activate
gcli
```

`gcli` launches the interactive REPL shell directly. There are no one-shot
command-line arguments — all interaction happens within the running session.

---

## REPL Interface

### Screen Layout

```
┌──────────────────────────────────────────────────────────────┐
│  [Project: Alpha]  ›  [Route: 1.1]  ›  [Stage: Reaction]    │  ← status bar
│  MODE: route                                                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   (output pane — command results, lists, dashboards)         │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  > /                                                         │  ← input line
└──────────────────────────────────────────────────────────────┘
```

- **Status bar** — breadcrumb showing current context; updates on navigation
- **Output pane** — command results; clears and redraws on each command
- **Input line** — slash-command input; `>` prompt; text accumulates as typed

### Navigation Model

The application has three top-level tracks:

| Track | Description | Entry |
|-------|-------------|-------|
| **Project** | Navigate projects, routes, stages, components, risks | Home screen (default) |
| **Library** | Browse and manage materials, NCRM, counterions | `/library` from anywhere |
| **Admin** | Bulk imports, database maintenance | `/admin` from home only |

**Navigation hierarchy (Project track):**

```
Home
  └── Project (selected from list or /select)
        ├── Route Mode → (route selected from list or /route R.P)
        │     ├── Stage Focus (/focus stage <name>)
        │     │     └── Component Focus (/focus component <name>)
        │     └── Risk Mode (/risks)
        └── Risk Mode (project-level summary)
```

**Arrow key navigation** is active only on list screens (Home, Route selection):

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move cursor through list items |
| `Enter` | Confirm selection of highlighted item |

List screens show two sections: **Recents** (last used, top) and **All** (alphabetical, below).

### Escape Navigation

| Action | Effect |
|--------|--------|
| First `Esc` | Clears current input buffer. Shows: `[ESC] Press Escape again to return to <parent>.` |
| Second `Esc` within ~2 seconds | Navigates up one level in the context stack |
| Timeout (>2 seconds) | Message clears; normal input resumes |
| `/home` | Jump directly to the home screen from any depth |

If a guided prompt (e.g. `/add`) is in progress, first `Esc` also shows:
`Warning: unsaved input will be lost.`

---

## Command Reference

### Global Commands

Available from any mode:

| Command | Description |
|---------|-------------|
| `/home` | Return to the home screen |
| `/library [materials\|ncrm\|counterions]` | Switch to library track |
| `/help [command]` | Show help for all commands or a specific command |
| `/quit` | Exit the application (unsaved data guard applies) |

### Home Screen

Displays two lists: **Recents** (last 5 projects) and **All Projects**.

Use arrow keys to navigate and `Enter` to select, or type:

```
/select <project name>    — select a project by name (partial match supported)
/admin                    — enter admin sub-mode
/library                  — switch to library track
/help                     — show all commands
/quit                     — exit
```

### Project Screen

Shown after selecting a project. Displays: project name, material, therapy area,
number of routes, and a risk summary table.

```
/route [R.P]              — enter route selection (or go direct to route R.P)
/risks                    — enter project-level risk summary
/select <project>         — switch to a different project
/library                  — switch to library track
```

### Route View

Primary working mode. Displays the ASCII process layout and a risk dashboard.

#### Navigation

```
/risks                    — view manufacturing process-level risks
/focus stage <name>       — focus on a specific stage
/focus component <name>   — focus on a specific component
/focus process            — focus on process-level risks
```

#### Listing

```
/list stages              — list all stages in this route
/list components          — list all components in this route
/list risks               — list all risks for this route (all levels)
/list ncrm                — list all NCRMs linked to stages in this route
```

#### Creating

```
/add stage <name> --number N           — add a stage to this route
/add component <name>                  — add a component (guided prompt)
/add risk                              — add a risk (guided prompt, asks level)
/add risk stage <name>                 — add a risk to a specific stage
/add risk component <name>             — add a risk to a specific component
/add risk process                      — add a process-level risk
/add stage-component                   — link a stage and component (guided)
/add stage-ncrm                        — link a stage and NCRM (guided)
```

#### Editing and Deleting

```
/edit                     — edit the current route (guided prompt)
/edit stage <name>        — edit a specific stage
/edit component <name>    — edit a specific component
/delete stage <name>      — delete a stage (with confirmation)
/delete component <name>  — delete a component (with confirmation)
```

#### Searching

```
/search <query>           — search for stages or components by name
```

### Stage Focus View

Shown after `/focus stage <name>`. Displays stage details, linked components,
NCRMs, and risks table.

```
/add risk                 — add a risk to this stage (guided prompt)
/add ncrm <name>          — link an NCRM to this stage (guided prompt)
/add component <name>     — link a component to this stage
/list risks               — show risks for this stage
/list components          — show components linked to this stage
/list ncrm                — show NCRMs linked to this stage
/edit                     — edit this stage
/delete                   — delete this stage (with confirmation)
```

### Component Focus View

Shown after `/focus component <name>`. Displays component details, salt data,
and risks table.

```
/add risk                 — add a risk to this component (guided prompt)
/add salt                 — add salt formation data (guided prompt)
/list risks               — show risks for this component
/edit                     — edit this component
/delete                   — delete this component (with confirmation)
```

### Risk Mode

Entered via `/risks` from project, route, stage, or component context. Displays
a filterable risk table.

```
/add risk                 — add a new risk (guided prompt)
/edit --id <N>            — edit risk by ID shown in table
/delete --id <N>          — delete risk by ID (with confirmation)
/filter type <TYPE>       — filter by risk type (Safety, Quality, Environment)
/filter level <N>         — show only risks at level N or above
/sort level               — sort risks by current level (descending)
```

### Library Track

Entered via `/library` from any screen.

```
/library materials        — browse materials
/library ncrm             — browse NCRM library
/library counterions      — browse counterions
```

**Within library sub-modes:**

```
/list                     — list all entries (with optional --limit N)
/search <query>           — search by name
/add                      — add an entry (guided prompt)
/edit <name>              — edit an entry (guided prompt)
/delete <name>            — delete an entry (with confirmation)
/show <name>              — show full details for an entry
/filter has-smiles        — show only entries with SMILES
/filter no-smiles         — show only entries without SMILES
```

**Material-specific:**

```
/add material <name> [--smiles SMILES] [--alias ALIAS] [--enable-dmta]
/edit material <name> [--set-name NAME] [--set-smiles SMILES] [--add-alias ALIAS]
```

**NCRM-specific:**

```
/add ncrm --display-name NAME --common-name NAME [--alias ALIAS] [--smiles SMILES]
```

**Counterion-specific:**

```
/add counterion <name> [--smiles SMILES] [--alias ALIAS]
```

### Admin Sub-mode

Entered via `/admin` from the **home screen only**.

#### Bulk Import

All import commands support `--skip-errors` and `--dry-run` flags.

```
/admin import materials <file.csv>
/admin import ncrm <file.csv>
/admin import counterions <file.csv>
/admin import projects <file.csv>
/admin import stages <file.csv>
/admin import components <file.csv>
/admin import stage-components <file.csv>
/admin import stage-ncrm <file.csv>
/admin import component-salts <file.csv>
```

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview import without writing to database |
| `--skip-errors` | Continue processing remaining rows on row failure |

#### Database Maintenance

```
/admin db analyze               — check SMILES canonicality across all materials
/admin db analyze --ncrm        — include NCRM library in analysis
/admin db canonicalize          — auto-canonicalize non-canonical SMILES using RDKit
/admin db canonicalize --dry-run  — preview canonicalization without writing
```

---

## Bulk CSV Import

### CSV Formats

#### Materials

```csv
name,smiles,aliases
Aspirin,CC(=O)Oc1ccccc1C(=O)O,Acetylsalicylic Acid;ASA
Ibuprofen,CC(C)Cc1ccc(C(C)C(=O)O)cc1,Advil;Motrin
```

Multiple aliases are separated by semicolons.

#### Projects

```csv
name,therapy_area,material_name
Project Alpha,Oncology,Aspirin
Project Beta,CVRM,Ibuprofen
```

#### Manufacturing Processes

```csv
project_name,route_number,process_number
Project Alpha,1,1
Project Alpha,1,2
```

#### Stages

```csv
project_name,route_number,process_number,stage_name,stage_number
Project Alpha,1,1,Reaction,1
Project Alpha,1,1,Purification,2
```

#### NCRM Library

```csv
display_name,common_name,aliases,interpret_chemically,smiles
Sodium bicarbonate,NaHCO3,Baking soda;Bicarb,false,
Palladium on carbon,Pd/C,,true,
```

#### Counterions

```csv
name,smiles,aliases
Chloride,[Cl-],Cl-;chloride anion
Sodium,[Na+],Na+
```

---

## Guided Prompts

Commands like `/add risk` enter a **guided prompt mode** where the REPL asks for
each required field one at a time.

Example `/add risk` flow:

```
> /add risk

  Adding risk to: Route 1.1

  Risk type [Safety / Quality / Environment]: Safety
  Risk name: Explosion hazard
  Description (optional): Pressure build-up during nitration step
  Current risk level [1-10]: 8
  Proposed mitigation (optional): Install pressure relief valve
  Mitigated risk level [1-10]: 3

  [PREVIEW]
  ─────────────────────────────────────
  Type    : Safety
  Name    : Explosion hazard
  Level   : 8 → 3 (mitigated)
  ─────────────────────────────────────
  Confirm? [y/n]: y

  ✓ Risk created.
```

Press `Esc` twice during a guided prompt to abort without saving.

---

## Entity Reference

### Therapy Areas

Valid values for `therapy_area` (case-sensitive):

```
Oncology
CVRM
Respiratory and Immunology
Vaccines and Immune Therapies
Rare Diseases
```

### NCRM Roles

Valid values for NCRM role:

```
reagent
catalyst
solvent
additive
internal_standard
```

---

## SMILES and Chemistry

The application uses [RDKit](https://www.rdkit.org/) for SMILES handling:

- **Validation** — SMILES strings are validated on input; invalid SMILES are rejected
- **Canonicalization** — SMILES are stored in canonical form
- **Auto-detection** — material search accepts SMILES strings alongside names and UUIDs
- **Analysis** — `/admin db analyze` reports non-canonical SMILES across all materials

RDKit must be installed in the virtual environment:

```bash
~/.venvs/riskworks/bin/pip install rdkit>=2023.3.1
```

---

## DMTA Enrichment

When creating materials with `--enable-dmta`, the application queries an
external DMTA (Design–Make–Test–Analyse) service to auto-populate SMILES
notation and synonyms.

Configure via environment variables:

```bash
export DMTA_API_URL="https://dmta.example.com/api"
export DMTA_API_KEY="your-api-key-here"
```

If `DMTA_API_URL` is not set, enrichment is silently skipped.

---

## Session State

The application persists navigation context between sessions in a JSON file
(default: `~/.gcli/session.json`).

Stored data:
- Recent projects (last 5 visited, in order of last use)
- Recent routes per project (last N used per project)
- Last active context (track, project ID, process ID)

The file is created automatically on first run. If missing or corrupt, the
application starts fresh at the home screen without error.

Customize the path:

```bash
export GCLI_SESSION_PATH="$HOME/.gcli/session.json"
```

---

## Development

### Code Quality Gates

**All commands use `~/.venvs/riskworks/bin/python` — never system Python.**

```bash
# Lint
~/.venvs/riskworks/bin/python -m ruff check src/ tests/

# Format check
~/.venvs/riskworks/bin/python -m ruff format --check src/ tests/

# Type checking
~/.venvs/riskworks/bin/python -m mypy src/governance_cli/

# Lint (pylint)
~/.venvs/riskworks/bin/python -m pylint src/governance_cli/

# All quality gates in one shot
~/.venvs/riskworks/bin/python -m ruff check src/ tests/ && \
~/.venvs/riskworks/bin/python -m ruff format --check src/ tests/ && \
~/.venvs/riskworks/bin/python -m mypy src/governance_cli/ && \
~/.venvs/riskworks/bin/python -m pylint src/governance_cli/ && \
~/.venvs/riskworks/bin/python -m pytest tests/ -x
```

Error suppression policy:
- **Global suppression is forbidden** — no file-level `# pylint: disable` or `mypy ignore_errors`
- **Inline suppression** only when refactoring is genuinely impossible, with a justification comment

### Running Tests

```bash
# Run all tests
~/.venvs/riskworks/bin/python -m pytest tests/ -v

# Run only unit tests (no database)
~/.venvs/riskworks/bin/python -m pytest tests/ -m unit -v

# Run only integration tests
~/.venvs/riskworks/bin/python -m pytest tests/ -m integration -v

# Stop on first failure
~/.venvs/riskworks/bin/python -m pytest tests/ -x
```

### Project Structure

```
src/
└── governance_cli/
    ├── __init__.py
    ├── __main__.py              # Entry point: init DB, load session, launch REPL
    ├── repl/                    # Interactive REPL shell layer
    │   ├── loop.py              # Main event loop (blessed inkey, key routing)
    │   ├── screen.py            # Screen manager (status bar, output pane, input line)
    │   ├── context.py           # Navigation context state machine + breadcrumb
    │   ├── commands.py          # Slash command parser and dispatcher
    │   ├── session_state.py     # JSON-backed session persistence
    │   ├── escape_handler.py    # Double-escape navigation logic
    │   ├── list_navigator.py    # Arrow-key list widget
    │   └── renderers/           # Output content renderers
    ├── operations/              # Async business logic (16 modules)
    ├── model/                   # SQLModel table definitions
    │   ├── tables.py
    │   └── enums.py
    ├── schema/                  # Pydantic create/update contracts
    ├── database/                # Session management
    ├── config/                  # Environment settings
    ├── service/                 # External service integrations
    └── utils/                   # Console formatting and helpers
tests/
├── conftest.py
├── operations/
├── repl/
└── utils/
pyproject.toml
CHANGELOG.md
README.md
```

---

## Versioning

This project follows [Semantic Versioning 2.0.0](https://semver.org/).

| Change | Version bump |
|--------|-------------|
| Removed/renamed commands, incompatible schema migrations | `MAJOR` |
| New entity, new command, new optional flag | `MINOR` |
| Bug fix, documentation, internal refactor | `PATCH` |

Version is defined only in `pyproject.toml`. Read at runtime:

```python
from importlib.metadata import version
__version__ = version("governance-cli")
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full history.

---

## Exit

```
/quit       — clean exit (saves session state, prompts if unsaved changes)
Ctrl+C      — interrupt exit (session state saved)
Ctrl+D      — EOF exit (session state saved)
```
