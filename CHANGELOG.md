# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Second example project: first-run bootstrap now also seeds the
  Osimertinib (Tagrisso) synthesis (AstraZeneca AZD9291) alongside the ibuprofen
  example — a convergent 9-stage oncology route (15 materials, 9 stages, 30
  stage→NCRM links). Committed as
  `riskmanager_cli/data/seed/example_project_osimertinib.json` and loaded via the
  same `seed_example_project` machinery; `load_example_project` now takes a
  filename and bootstrap iterates over `EXAMPLE_PROJECT_SEED_FILES`. The single
  "Seeding example project entities" progress line now aggregates the entity
  counts of every example project. The NCRM seed library gains a `2-pentanol`
  entry (Stage 1 SNAr solvent), raising its count to 327.
- Example project seeding: first-run bootstrap now seeds a worked example
  project — the Boots ibuprofen synthesis — after the reference libraries, so a
  new database opens with a real 9-stage manufacturing process to explore. The
  graph (14 materials, project, process, stages, components, and stage→NCRM
  links) is committed as `riskmanager_cli/data/seed/example_project.json` and
  loaded via `operations.seed_operations.seed_example_project`; the bootstrap
  progress box gains a fourth "Seeding example project" line. The NCRM seed
  library gains a `ketene` entry (used by the acetic-anhydride branch), raising
  its count to 326.
- Selectable library tables: the materials, NCRM and counterion subsections now
  render as navigable, alphabetised box tables with a `>` selection caret. ↑/↓
  move the caret and Enter (or `^E`) edits the highlighted row inline, replacing
  the previous "which one?" chooser; `^X` deletes and `^O` shows the selected
  row. Tables gain Name · Display name · Aliases · SMILES columns, with
  chemically-rendered display names (stoichiometric subscripts, e.g. `H₂SO₄`)
  via `utils.formula_parser.render_chemical_formula` and per-entry alias counts
  from new `*_alias_counts` operations.
- First-run reference-library seeding: when no database file exists at the
  resolved path, the app now creates the schema and seeds the default
  counterion (24) and NCRM (327) libraries from committed JSON
  (`riskmanager_cli/data/seed/*.json`), showing a live initialisation progress
  box. Subsequent launches detect the existing file and skip seeding.
  New: `operations/seed_operations.py`, `repl/bootstrap.py`, and
  `config.settings.get_db_path`
- Stage 9 test suite: 75 tests across `tests/operations/`, `tests/repl/`, and
  `tests/utils/` covering material, project, and component CRUD operations;
  SMILES validation; context-stack navigation; session state persistence; and
  CSV parsing helpers
- `tests/conftest.py` with `mock_session`, `db_session`, and `temp_env` fixtures
- Testing guide section in `README.md` documenting test markers and quality gates
- Initial project scaffold: `pyproject.toml`, `.gitignore`, `CHANGELOG.md`
- Contributor guide (`AGENTS.md`) with mandatory architecture, build, semver,
  code quality, and quality gate requirements
- `CLAUDE.md` pointing Claude Code at `AGENTS.md`

### Changed

- Documentation tidyup: renamed `.github/copilot-instructions.md` →
  `AGENTS.md` (tool-agnostic); pruned `blueprint/` from 12 docs to the four
  carrying unique design rationale (`00-overview`, `01-architecture`,
  `02-data-model`, `03-repl-ux`), reframing it as a design reference rather than
  a greenfield build spec

### Removed

- Superseded blueprint docs (stack, environment, enums, cli-reference,
  operations-patterns, code-quality, semver, persistence-layer) and the
  completed `partially-implemented-plan.md` build plan

---

## [0.3.0] — Initial greenfield target

_Greenfield implementation from blueprint. See `blueprint/` directory for the
full specification._

### Added

- Seven-layer interactive REPL architecture using `blessed`
- SQLite persistence via SQLAlchemy async + `aiosqlite`
- Entities: Material, Project, ManufacturingProcess, Stage, Component,
  ManufacturingProcessRisk, StageRisk, ComponentRisk, ComponentSalt,
  NcrmLibrary, StageNcrm, StageComponent, Counterion
- Full slash-command grammar: `/select`, `/route`, `/risks`, `/focus`, `/add`,
  `/edit`, `/delete`, `/list`, `/search`, `/filter`, `/library`, `/admin`,
  `/home`, `/help`, `/quit`
- Bulk CSV import via `/admin import` commands
- SMILES canonicalization and validation via RDKit
- Optional DMTA enrichment via external HTTP service
- JSON-backed session state at `~/.rmgr/session.json`
- Context-aware navigation: Project → Route → Stage/Component hierarchy

### Removed (vs reference implementation)

- `riskmanager_server` wheel dependency (all models re-implemented locally)
- PostgreSQL / asyncpg (replaced by SQLite / aiosqlite)
- FastAPI / HTTP server (REPL-only application)
- `argparse` / `argcomplete` (replaced by REPL command dispatcher)
- `project_status` and `interaction` tables (not needed for single-user app)
- All `*_version` audit tables (PostgreSQL trigger dependency removed)
