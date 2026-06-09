# Code Quality Standards

## Overview

This document defines the conventions, standards, and best practices for the
greenfield implementation. All code should adhere to these standards for
consistency, maintainability, and readability.

---

## Python Version and Style

- **Minimum Python version:** `>=3.10`
- **Line length:** 100 characters
- **Linter/formatter:** `ruff` (replaces flake8 + isort + black)
- **Type hints:** Required on all public functions; use `Optional[X]` or `X | None` (Python 3.10+)
- **String quotes:** Double quotes preferred
- **Import order:** stdlib → third-party → local (ruff enforces)

### Ruff Configuration

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
# E: pycodestyle errors
# F: pyflakes
# I: isort
# N: pep8-naming
# W: pycodestyle warnings
# UP: pyupgrade (enforce modern syntax)
```

---

## File Naming Conventions

| Layer | Pattern | Example |
|-------|---------|---------|
| REPL modules | `repl/<name>.py` | `repl/loop.py`, `repl/screen.py` |
| REPL renderers | `repl/renderers/<entity>_renderer.py` | `repl/renderers/project_renderer.py` |
| Operations | `<entity>_operations.py` | `material_operations.py` |
| Tests (operations) | `test_<entity>.py` | `test_material.py` |
| Tests (REPL) | `test_<module>.py` | `test_commands.py`, `test_screen.py` |

### Function Naming Conventions

| Category | Pattern | Example |
|----------|---------|---------|
| REPL command handler | `handle_<command>(args, context, env)` | `handle_add_risk` |
| REPL renderer | `render_<entity>(data, term)` | `render_project_summary` |
| Operation (async) | `<action>_<entity>(...)` | `create_material`, `get_material_by_name` |
| Private REPL helper | `_<name>(...)` | `_draw_recents_section` |

---

## Docstring Conventions

Every module, public class, and public function must have a docstring.

### Module-Level Docstrings

```python
"""
Brief one-line description of the module.

More detailed explanation covering:
- Primary purpose and scope
- Key responsibilities
- Important behavioral notes or constraints

Why this exists:
    Explain the design reason behind having this module.
"""
```

### Function Docstrings

```python
def function_name(param1: Type, param2: Type) -> ReturnType:
    """Brief one-line description of what the function does.

    Optional longer explanation when the behavior is non-obvious.
    Cover edge cases, design decisions, or important constraints.

    Args:
        param1: Description including constraints and expected format.
        param2: Description with important details.

    Returns:
        Description of the return value. For Optional returns, describe
        when None is returned.

    Raises:
        ExceptionType: When and why this exception is raised.

    Example:
        >>> result = function_name("input", 42)
        >>> print(result)
        'expected output'
    """
```

### Class Docstrings

```python
class ClassName:
    """Brief description of the class purpose.

    Longer explanation covering primary use case, key behaviors,
    and important lifecycle notes.

    Attributes:
        attr_name: Description of the attribute, type, and constraints.
        other_attr: Description with important details.
    """
```

### "Why this exists" Pattern

For non-obvious design choices, include a "Why this exists" section:

```python
def update_material_by_search(search_value: str, ...) -> Optional[Material]:
    """Search for a material by ID, name, or SMILES and update it.

    Why this exists:
        Different contexts provide different identifiers (UUIDs from exports,
        SMILES from chemical searches, names from user input). Auto-detection
        eliminates the need for explicit type specification in most cases.
    """
```

### Do Not Over-Comment

- Comment only non-obvious logic
- Prefer clear code over explanatory comments
- Do not repeat what the code does — explain **why**

```python
# BAD — states the obvious
materials = await Material.get_where(session, Material.name == name)  # get by name

# GOOD — explains a non-obvious decision
# Use first match only; uniqueness is enforced by DB constraint
return materials[0] if materials else None
```

---

## Error Handling Conventions

### Operations Layer (print + return None/False)

Operations functions absorb errors, print a user-friendly message, and return
a sentinel value (`None`, `[]`, `False`). They **do not re-raise**.

```python
async def get_material_by_id(material_id: UUID, env: Environment, verbose: bool) -> Optional[Material]:
    try:
        async with get_db_session(env, verbose) as session:
            results = await Material.get_where(session, Material.id == material_id)
            return results[0] if results else None
    except Exception as e:
        print_error(f"Failed to get material by ID: {e}")
        return None
```

### Command Handlers (check return, render output)

Command handlers in `repl/commands.py` check the operations result and return a
`RenderableContent` object that the `ScreenManager` renders.

```python
def handle_add_material(args: CommandArgs, context: ContextManager, env: Environment) -> RenderableContent:
    result = run_async(create_material(args.name, args.smiles, env))
    if result:
        return RenderableContent.success(f"Created material '{result.name}' (ID: {result.id})")
    return RenderableContent.error("Failed to create material.")  # error already printed by operations layer
```

### Connectivity Error Detection

Use `is_connectivity_error(exc)` to provide context-specific messaging:

```python
except Exception as exc:
    if is_connectivity_error(exc):
        print("Temporary database connectivity issue. Please retry shortly.")
    raise
```

---

## Console Output Conventions

**In the operations layer:** use `print_error`, `print_warning`, `print_info` from
`utils/console_formatting.py` for diagnostic output (errors, warnings). These are
the only direct terminal writes from the operations layer.

**In the REPL layer:** all screen output goes through `ScreenManager`. Do NOT call
`print()` or `print_*()` functions from `repl/` modules. Return `RenderableContent`
objects instead, and let `ScreenManager.draw_output()` handle rendering.

```python
# CORRECT — operations layer (error feedback)
async def create_material(name: str, ...) -> Optional[Material]:
    try:
        ...
    except Exception as e:
        print_error(f"Failed to create material: {e}")
        return None

# CORRECT — REPL command dispatcher (structured output)
def handle_list_materials(args, context, env) -> RenderableContent:
    materials = run_async(list_materials(env=env))
    return RenderableContent.table(
        headers=["Name", "SMILES", "ID"],
        rows=[(m.name, m.smiles or "—", str(m.id)) for m in materials],
    )

# WRONG — never print directly from REPL layer
def handle_list_materials(args, context, env):
    materials = run_async(list_materials(env=env))
    for m in materials:
        print(m.name)  # ← never do this in repl/
```

### `RenderableContent` types

| Factory method | Use for |
|----------------|---------|
| `RenderableContent.success(message)` | Confirmed operation (green) |
| `RenderableContent.error(message)` | Failure (red) |
| `RenderableContent.warning(message)` | Non-fatal issue (yellow) |
| `RenderableContent.info(message)` | Status / dry-run preview (cyan) |
| `RenderableContent.table(headers, rows)` | Tabular data |
| `RenderableContent.text(lines)` | Plain multi-line text |
| `RenderableContent.dashboard(sections)` | Mixed layout (route view, risk dashboard) |

---

## Async Patterns

### REPL loop is synchronous

The REPL event loop runs synchronously (using `blessed.inkey()` for blocking key
capture). Async DB operations are dispatched from within the sync loop via:

```python
def run_async(coro):
    """Bridge: call an async coroutine from the synchronous REPL loop."""
    return asyncio.get_event_loop().run_until_complete(coro)
```

**Rules:**
- One event loop is created at startup and reused throughout
- Never nest `run_until_complete` calls
- All operations functions must be `async def`
- Sessions are always opened with `async with get_db_session(...) as session:`

### Always `async def` in operations

```python
# CORRECT
async def create_material(name: str, env: Environment, verbose: bool) -> Optional[Material]:
    async with get_db_session(env, verbose) as session:
        ...

# WRONG — sync functions cannot use async sessions
def create_material(name: str, env: Environment, verbose: bool) -> Optional[Material]:
    ...
```

### Session per operation (not shared)

```python
# CORRECT — each operation opens its own session
async def create_material(...):
    async with get_db_session(env) as session:
        ...

async def get_material_by_name(...):
    async with get_db_session(env) as session:
        ...

# WRONG — sharing sessions between operations creates coupling
async def create_material(session: AsyncSession, ...):  # don't pass sessions
    ...
```

### `run_async()` instead of `asyncio.run()`

The async/sync boundary is managed by a shared event loop. Use `run_async()`
from `repl/loop.py` within the REPL, not `asyncio.run()`:

```python
# In repl/commands.py — CORRECT
from .loop import run_async

def handle_add_material(args, context, env):
    result = run_async(create_material(args.name, args.smiles, env))
    ...

# WRONG — asyncio.run() must not be called from within the running loop
def handle_add_material(args, context, env):
    result = asyncio.run(create_material(args.name, args.smiles, env))  # ← raises error
    ...
```

---

## Testing Standards

### Test Setup

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["asyncio: asyncio mark", "unit: unit tests", "integration: integration tests"]
```

### Test File Structure

```
tests/
├── conftest.py              # Shared fixtures
├── operations/
│   ├── test_material.py
│   ├── test_project.py
│   ├── test_component.py
│   └── ...
├── repl/
│   ├── test_commands.py
│   ├── test_context.py
│   ├── test_session_state.py
│   └── ...
└── utils/
    ├── test_parsing.py
    └── ...
```

### `conftest.py` Fixtures

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

@pytest.fixture
def mock_session() -> AsyncMock:
    """Async mock session for unit tests (no database required)."""
    session = AsyncMock(spec=AsyncSession)
    session.get_where = AsyncMock(return_value=[])
    session.get_all = AsyncMock(return_value=[])
    return session

@pytest_asyncio.fixture
async def db_session():
    """Real in-memory SQLite session for integration tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

### Test Naming

- Test files: `test_<module>.py`
- Test functions: `test_<what_is_being_tested>_<expected_outcome>()`

```python
async def test_create_material_returns_material_with_id():
    ...

async def test_create_material_with_duplicate_name_returns_none():
    ...

async def test_parse_csv_with_semicolon_delimiter_parses_aliases():
    ...
```

### Unit vs Integration Tests

```python
@pytest.mark.unit
async def test_detect_search_type_returns_id_for_uuid():
    """Unit test — no database required."""
    result = detect_search_type("550e8400-e29b-41d4-a716-446655440000")
    assert result == "id"


@pytest.mark.integration
async def test_create_material_persists_to_database(db_session):
    """Integration test — requires real session."""
    material = await create_material_in_session(db_session, name="Aspirin")
    assert material.id is not None
    assert material.name == "Aspirin"
```

---

## Import Conventions

### Preferred Import Style

```python
# Standard library
import os
import asyncio
from typing import Optional, List
from uuid import UUID, uuid4

# Third-party
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Text
from pydantic import BaseModel

# Local (relative imports within the package)
from ..config.settings import Environment
from ..database.db_session import get_db_session
from ..utils.console_formatting import print_error, print_success
from ..model.tables import Material
from ..schema.create import MaterialCreate
```

### Avoid Wildcard Imports

```python
# WRONG
from ..model.tables import *

# CORRECT
from ..model.tables import Material, Project, Stage
```

---

## Git Commit Conventions

All commits include a co-author trailer:

```
feat: add manufacturing process risk sub-table

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

Prefix conventions:
| Prefix | Use |
|--------|-----|
| `feat:` | New feature or capability |
| `fix:` | Bug fix |
| `docs:` | Documentation changes |
| `refactor:` | Code restructuring without behavior change |
| `test:` | Test additions or changes |
| `chore:` | Build, tooling, config changes |
