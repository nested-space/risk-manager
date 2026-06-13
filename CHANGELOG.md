# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

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
