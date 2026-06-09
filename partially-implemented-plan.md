# Governance CLI — Implementation Plan

## Problem Statement

Implement the `governance-cli` application from scratch using the 11-document blueprint in
`blueprint/`. The result is a `blessed`-based interactive REPL shell for managing
pharmaceutical manufacturing governance data, backed by SQLite via SQLAlchemy async.

## Mandatory Constraints

- Virtual environment: `~/.venvs/riskworks` — **NEVER** use system Python
- All Python commands must be prefixed: `~/.venvs/riskworks/bin/python` or activate venv first
- `pip install` always targets the venv: `~/.venvs/riskworks/bin/pip install ...`
- Python >= 3.10 required

---

## Approach

Build in 9 stages. README.md is updated at the end of each stage. Each stage is
independently testable before the next begins.

---

## Stages

### Stage 0 — Bootstrap (repo skeleton + mandatory governance files)

Create these files **first**, before any code:

| File | Purpose |
|------|---------|
| `.github/copilot-instructions.md` | Mandatory requirements: architecture, build, semver, code quality, quality gates |
| `.gitignore` | Exclude build artefacts, venvs, DB files, caches |
| `README.md` (stub) | Initial user documentation stub with installation and usage sections |
| `pyproject.toml` | Package metadata, dependencies, ruff + pytest config |
| `CHANGELOG.md` | Keep-a-Changelog format, starting at `[Unreleased]` |
| `LICENSE` | MIT or applicable license |

### Stage 1 — Package Skeleton

Create all empty `__init__.py` files and stub modules matching the target file structure
from `blueprint/00-overview.md`. No logic — just the import tree.

Directory structure:
```
src/governance_cli/
  __init__.py  __main__.py
  repl/  operations/  model/  schema/  database/  config/  service/  utils/
tests/
  conftest.py
  operations/  repl/  utils/
```

### Stage 2 — Configuration Layer

Implement:
- `config/settings.py` — `Environment` enum, `build_db_url()`, `get_session_path()`

Per blueprint `02-environment.md`.

### Stage 3 — Database & Model Layer

Implement in order (dependencies flow upward):

1. `model/enums.py` — `TA`, `NcrmRole`
2. `model/tables.py` — all 13 SQLModel table classes + `CRUDMixin` (from `10-persistence-layer.md` and `04-data-model.md`)
3. `database/connection.py` — engine factory with SQLite PRAGMAs
4. `database/db_session.py` — `get_db_session()` async context manager
5. `database/exceptions.py` — `is_connectivity_error()`
6. `schema/create.py` — Pydantic create schemas for all entities
7. `schema/update.py` — Pydantic update schemas for all entities

### Stage 4 — Utilities Layer

Implement:
- `utils/console_formatting.py` — `print_error`, `print_warning`, `print_info`, `print_success`, `print_key_value`
- `utils/parsing.py` — CSV parsing helpers
- `utils/formula_parser.py` — molecular formula helpers
- `utils/manufacturing_layout_engine.py` — ASCII route layout generator

### Stage 5 — Operations Layer

Implement all 16 async operations modules. Each follows the pattern in `07-operations-patterns.md`:
- async functions, session-per-operation, print_error on failure, return None/[]

Order (leaf → parent):
1. `smiles_operations.py`
2. `counterion_operations.py`
3. `ncrm_library_operations.py`
4. `material_operations.py`
5. `component_operations.py`
6. `component_risks_operations.py`
7. `component_salt_operations.py`
8. `stage_operations.py`
9. `stage_component_operations.py`
10. `stage_risk_operations.py`
11. `stage_ncrm_operations.py`
12. `manufacturing_process_operations.py`
13. `manufacturing_process_risk_operations.py`
14. `project_operations.py`
15. `dmta_operations.py`
16. `visualization_operations.py`

### Stage 6 — External Services Layer

Implement:
- `service/DmtaService.py` — async HTTP client using `httpx`
- `service/SmilesComparisonResult.py` — result dataclass

### Stage 7 — REPL Layer

Implement in dependency order:
1. `repl/session_state.py` — JSON-backed session persistence
2. `repl/context.py` — `ContextManager`, `ContextFrame`, `current_breadcrumb()`
3. `repl/screen.py` — `ScreenManager`, `RenderableContent` factory methods
4. `repl/list_navigator.py` — arrow-key list widget (Recents + All sections)
5. `repl/escape_handler.py` — double-escape timing logic
6. `repl/renderers/` — 5 renderer modules
7. `repl/commands.py` — slash command parser + all handlers (guided prompts)
8. `repl/loop.py` — main event loop, `run_async()` bridge

### Stage 8 — Entry Point

Implement `__main__.py`:
- Read env vars → build `Environment` → `init_db()` → load `SessionState` → `blessed.Terminal()` → `start_repl()`
- Expose `cli_main()` entry point

### Stage 9 — Tests

Write tests following `08-code-quality.md`:
- `tests/conftest.py` — `mock_session` and `db_session` fixtures
- `tests/operations/` — unit + integration tests per operations module
- `tests/repl/` — unit tests for commands, context, session_state
- `tests/utils/` — unit tests for parsing, formula_parser

---

## Quality Gates (enforced at every stage)

All commands use `~/.venvs/riskworks/bin/python` — **NEVER** system Python.

| Tool | Command | Must produce |
|------|---------|-------------|
| Ruff lint | `~/.venvs/riskworks/bin/python -m ruff check src/ tests/` | 0 errors |
| Ruff format | `~/.venvs/riskworks/bin/python -m ruff format --check src/ tests/` | 0 diffs |
| Pylint | `~/.venvs/riskworks/bin/python -m pylint src/governance_cli/` | 0 errors/warnings (score 10/10) |
| Mypy | `~/.venvs/riskworks/bin/python -m mypy src/governance_cli/` | 0 errors |
| Pytest | `~/.venvs/riskworks/bin/python -m pytest tests/ -x` | all green |

### Suppression Policy (mandatory)

- **Global suppression is FORBIDDEN** — no `# pylint: disable=...` at file/module scope, no `[[tool.mypy]] ignore_errors = true`
- **Inline suppression is permitted ONLY** when refactoring is genuinely impossible (e.g. Alembic runtime injection, blessed terminal internals, SQLAlchemy dynamic metaclass attributes)
- Every inline suppression **MUST** include a justification comment on the same line:
  ```python
  op.add_column(...)  # pylint: disable=no-member  # Alembic virtual op not injected until runtime
  ```
- Refactor code to fix the underlying issue before resorting to any suppression

### Additional invariants

- No bare `print()` in `repl/` modules (only `ScreenManager.draw_*()`)
- All public functions, classes, and modules have docstrings

---

## README Update Schedule

| After Stage | README sections to add/update |
|-------------|-------------------------------|
| Stage 0 | Installation prerequisites, venv setup |
| Stage 2 | Configuration (env vars reference) |
| Stage 3 | Database initialization |
| Stage 5 | Operations layer overview |
| Stage 7 | Full REPL command reference (mirrors `06-cli-reference.md`) |
| Stage 8 | Entry point / launch instructions |
| Stage 9 | Testing guide |

---

## Key Files Reference

| File | Blueprint Source |
|------|----------------|
| `pyproject.toml` | `01-stack.md` |
| `config/settings.py` | `02-environment.md` |
| `model/tables.py` | `04-data-model.md` |
| `model/enums.py` | `05-enums.md` |
| `repl/commands.py` | `06-cli-reference.md` |
| `operations/*` | `07-operations-patterns.md` |
| code quality rules | `08-code-quality.md` |
| versioning rules | `09-semver.md` |
| `database/db_session.py` | `10-persistence-layer.md` |
| `repl/screen.py`, `repl/loop.py` | `11-repl-ux.md` |
