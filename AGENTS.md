# Contributor Guide — `riskmanager-cli`

These rules are **mandatory** and apply to every contribution, AI-assisted (any
tool) or human. No exceptions without explicit project-owner approval documented
in the PR description.

For design rationale behind the architecture and schema, see `blueprint/`
(`01-architecture.md`, `02-data-model.md`, `03-repl-ux.md`).

---

## 1. Virtual Environment (MANDATORY)

**NEVER use the system Python interpreter.**

All Python commands MUST target the project virtual environment:

```bash
# Correct — always use the venv
~/.venvs/riskmanager/bin/python ...
~/.venvs/riskmanager/bin/pip install ...
~/.venvs/riskmanager/bin/ruff ...
~/.venvs/riskmanager/bin/mypy ...
~/.venvs/riskmanager/bin/pylint ...
~/.venvs/riskmanager/bin/pytest ...

# Alternative: activate first
source ~/.venvs/riskmanager/bin/activate
python ...  # now safe

# FORBIDDEN — system Python
python ...          # ← NEVER
python3 ...         # ← NEVER
/usr/bin/python3 ...  # ← NEVER
```

The virtual environment is located at `~/.venvs/riskmanager`.
It is NOT committed to the repository and NOT stored under the project root.
It must never appear in `.gitignore` because it is outside the repo.

---

## 2. Architecture

### Engine / application split

The TUI is split into two top-level packages with a single, enforced seam:

* **`repl_engine/`** — the **application-agnostic** terminal UI engine: event
  loop, screen drawing, viewport/scrolling, list navigation, the
  guided-prompt/picker forms engine, and layout primitives. It has **no
  knowledge of the risk-manager domain** and **MUST NOT import** from `repl/`,
  `operations/`, `model/`, `schema/`, `service/`, or `config/`. It may import
  only stdlib, `blessed`, and other `repl_engine` modules.
* **`repl/`** — the **application** layer: command dispatch, navigation context,
  session state, bootstrap, and the domain screen renderers. It depends on
  `repl_engine` and the operations/model layers.

The seam between them is the `ReplController` protocol
(`repl_engine/controller.py`). The engine's `start_repl(term, screen, controller)`
loop drives **any** object implementing that protocol; the application's
`CommandDispatcher` is the concrete implementation. This dependency inversion is
what keeps the engine domain-free.

### Layered Model

Each layer communicates ONLY with immediately adjacent layers.

```
Entry Point (__main__.py)            ── wires engine + application together
    └── REPL Loop (repl_engine/loop.py)         [engine] drives a ReplController
            ├── Screen Manager (repl_engine/screen.py)        [engine]
            ├── Forms / Modal (repl_engine/forms.py)          [engine]
            ├── Controller Protocol (repl_engine/controller.py) [engine, the seam]
            └── Command Dispatcher (repl/commands.py)         [application, implements ReplController]
                    ├── Context Manager (repl/context.py)
                    ├── Screen Renderers (repl/renderers/*.py)
                    └── Operations Layer (operations/*_operations.py)
                            └── Database Layer (database/, model/, schema/)
                                            [sidecar] Session State (repl/session_state.py)
```

### Layer Boundary Rules

| Rule | Enforcement |
|------|------------|
| `repl_engine/` MUST NOT import from `repl/`, `operations/`, `model/`, `schema/`, `service/`, `config/` | Engine stays domain-free; verify with the seam grep (see Quality Gates) |
| `repl/` and `repl_engine/` modules MUST NOT call `print()` directly | All screen output via `ScreenManager.draw_*()` |
| `repl/` modules MUST NOT open database sessions | Delegate to operations layer |
| Operations modules MUST NOT import from `repl/` or `repl_engine/` | No upward dependencies |
| `database/` and `model/` MUST NOT import from `operations/` | No circular deps |
| Entry point MUST NOT contain business logic | Config + wiring only |

### Source Layout

```
src/
└── riskmanager_cli/
    ├── __init__.py
    ├── __main__.py
    ├── repl_engine/          # application-agnostic TUI engine
    │   ├── loop.py
    │   ├── controller.py     # ReplController protocol (the seam)
    │   ├── screen.py
    │   ├── keys.py
    │   ├── forms.py
    │   ├── viewport.py
    │   ├── sticky_window.py
    │   ├── list_navigator.py
    │   └── layout/
    ├── repl/                 # application: dispatch, context, renderers
    │   ├── commands.py
    │   ├── context.py
    │   ├── session_state.py
    │   ├── bootstrap.py
    │   └── renderers/
    ├── operations/
    ├── model/
    ├── schema/
    ├── database/
    ├── config/
    ├── service/
    └── utils/
tests/
├── conftest.py
├── operations/
├── repl/                     # application tests
├── repl_engine/             # engine tests (mirror src/.../repl_engine)
└── utils/
```

`src/` layout is used. `pyproject.toml` configures `setuptools.packages.find`
with `where = ["src"]`.

---

## 3. Build

### Installing the Package

```bash
# Install in editable mode (development)
~/.venvs/riskmanager/bin/pip install -e ".[dev]"

# Install production dependencies only
~/.venvs/riskmanager/bin/pip install -e .
```

### Building a Distribution

```bash
~/.venvs/riskmanager/bin/python -m build
```

Produces `dist/riskmanager_cli-X.Y.Z-py3-none-any.whl` and `.tar.gz`.

### Entry Points

| Command | Maps to |
|---------|---------|
| `rmgr` | `riskmanager_cli.__main__:cli_main` |
| `riskmanager-cli` | `riskmanager_cli.__main__:cli_main` |

### Database Initialization

On first run, SQLite tables are created automatically via `init_db()` in
`__main__.py`. No manual schema setup is required.

For Alembic migrations (production):
```bash
~/.venvs/riskmanager/bin/alembic upgrade head
```

### Recommended Shell Setup

```bash
export APP_ENV=dev
export APP_DEV_DB_PATH="$HOME/.rmgr/riskmanager-dev.db"
export APP_PROD_DB_PATH="$HOME/.rmgr/riskmanager.db"
mkdir -p ~/.rmgr
```

---

## 4. Semantic Versioning

Version is defined **only** in `pyproject.toml`. Do NOT duplicate it in
`__init__.py` or any `__version__` variable. Read at runtime via:

```python
from importlib.metadata import version
__version__ = version("riskmanager-cli")
```

### Bump Rules

| Change type | Version component |
|-------------|------------------|
| Breaking: removed/renamed commands, incompatible schema migrations, renamed env vars | `MAJOR` |
| New capability: new entity, new command, new optional flag, new integration | `MINOR` |
| Bug fix, docs, formatting, internal refactor with identical behaviour | `PATCH` |

### Current Version

`0.3.0` (pre-1.0). Pre-1.0 versions may contain breaking changes; consumers
should pin to exact versions.

### Release Procedure

1. Update `version` in `pyproject.toml`
2. Update `CHANGELOG.md` (move `[Unreleased]` to new version section)
3. Commit: `chore: bump version to X.Y.Z`
4. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
5. Build: `~/.venvs/riskmanager/bin/python -m build`

---

## 5. Code Quality Standards

### Python Version

- Minimum: `>=3.10`
- Use modern syntax: `match`/`case`, `X | Y` unions, structural pattern matching

### Style

- Line length: **100 characters**
- String quotes: **double quotes** preferred
- Import order: stdlib → third-party → local (ruff enforces via `I` rules)
- Type hints: **required** on all public functions; use `X | None` (Python 3.10+)

### Docstrings (mandatory on all public modules, classes, and functions)

```python
def function_name(param1: Type, param2: Type) -> ReturnType:
    """Brief one-line description.

    Optional longer explanation for non-obvious behaviour.

    Args:
        param1: Description, constraints, expected format.
        param2: Description.

    Returns:
        Description. For Optional returns, describe when None is returned.

    Raises:
        ExceptionType: When and why raised.
    """
```

For non-obvious design choices, add a "Why this exists" section:

```python
def update_material_by_search(...):
    """Search for a material by ID, name, or SMILES and update it.

    Why this exists:
        Different contexts provide different identifiers. Auto-detection
        eliminates the need for explicit type specification in most cases.
    """
```

### Naming Conventions

| Category | Pattern | Example |
|----------|---------|---------|
| REPL command handler | `handle_<command>(args, context, env)` | `handle_add_risk` |
| REPL renderer | `render_<entity>(data, term)` | `render_project_summary` |
| Operation (async) | `<action>_<entity>(...)` | `create_material` |
| Private helper | `_<name>(...)` | `_draw_recents_section` |

### Comments

- Comment only **non-obvious logic** — explain *why*, not *what*
- Do NOT repeat what the code does
- Prefer clear code over explanatory comments

### Async Patterns

- All operations functions MUST be `async def`
- Each operation opens its own session via `async with get_db_session(...)`
- NEVER share sessions between operations
- NEVER call `asyncio.run()` from within the REPL loop — use `run_async()` from `repl/loop.py`

### Error Handling

- Operations layer: absorb exceptions, call `print_error()`, return `None`/`[]`/`False`
- REPL command layer: check operation return value, return `RenderableContent.error(...)` 
- REPL loop: NEVER exit the process on error (display in output pane, continue)
- Application exits only on `/quit`, `Ctrl+C`, or `Ctrl+D`

### Git Commit Conventions

```
feat: add manufacturing process risk sub-table
fix: correct CSV delimiter detection for semicolon-separated files
docs: update README with counterion import format
refactor: extract CRUDMixin to model/util.py
test: add integration tests for stage_ncrm_operations
chore: bump version to 0.4.0
```

Never add a `Co-authored-by:` trailer to commit messages.

---

## 6. Quality Gates (mandatory at every stage)

All commands MUST use `~/.venvs/riskmanager/bin/python`. Using system Python
invalidates the quality gate.

| Gate | Command | Required result |
|------|---------|----------------|
| Ruff lint | `~/.venvs/riskmanager/bin/python -m ruff check src/ tests/` | 0 errors |
| Ruff format | `~/.venvs/riskmanager/bin/python -m ruff format --check src/ tests/` | 0 diffs |
| Pylint | `~/.venvs/riskmanager/bin/python -m pylint src/riskmanager_cli/` | Score 10.00/10 |
| Mypy | `~/.venvs/riskmanager/bin/python -m mypy src/riskmanager_cli/` | 0 errors |
| Tests | `~/.venvs/riskmanager/bin/python -m pytest tests/ -x` | All green |
| Engine seam | `grep -rnE 'from \.\.(repl\|operations\|model\|schema\|service\|config)[. ]' src/riskmanager_cli/repl_engine/` | No matches (engine imports no application code) |

### Suppression Policy

**Global suppression is FORBIDDEN.**

The following are prohibited:
- `# pylint: disable=...` at module/file scope
- `[[tool.mypy]] ignore_errors = true` or `ignore_missing_imports = true` globally
- `# type: ignore` without a per-line justification
- `# noqa` without a per-line justification

**Inline suppression** is permitted ONLY when it is genuinely impossible to
refactor the code. Every inline suppression MUST include a justification comment:

```python
# CORRECT — justified inline suppression
op.add_column(...)  # pylint: disable=no-member  # Alembic virtual op not injected until runtime
term.move_xy(x, y)  # type: ignore[attr-defined]  # blessed Terminal attrs generated dynamically

# WRONG — no justification
result = session.execute(stmt)  # type: ignore
```

When a suppression is added, a TODO comment referencing the upstream issue is
encouraged:

```python
# pylint: disable=no-member  # SQLModel metaclass generates attrs at runtime (SQLModel#123)
```

---

## 7. Testing Standards

### Configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "asyncio: asyncio mark",
    "unit: unit tests (no database required)",
    "integration: integration tests (real SQLite in-memory session)",
]
```

### Fixtures

- `mock_session`: `AsyncMock(spec=AsyncSession)` — for unit tests
- `db_session`: real `sqlite+aiosqlite:///:memory:` session — for integration tests

### Test Naming

```python
async def test_<what_is_tested>_<expected_outcome>():
    ...

# Examples:
async def test_create_material_returns_material_with_id(): ...
async def test_create_material_with_duplicate_name_returns_none(): ...
```

### Marks

```python
@pytest.mark.unit       # no database; use mock_session
@pytest.mark.integration  # requires db_session fixture
```
