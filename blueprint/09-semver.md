# Semantic Versioning

## Current Version

`0.3.0` (pre-1.0)

---

## Versioning Scheme

This application follows [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH
```

| Component | When to increment |
|-----------|-------------------|
| `MAJOR` | Breaking changes: removed commands, renamed flags, incompatible schema migrations |
| `MINOR` | New backward-compatible capabilities: new commands, new optional flags, new entities |
| `PATCH` | Backward-compatible bug fixes, documentation updates, internal refactoring |

---

## Pre-1.0 Conventions

**Current status: pre-1.0 (`0.x.y`)**

During pre-1.0 development:
- Any version bump may contain breaking changes; strictly follow the intent below
  but know that consumers should pin to exact versions
- `MINOR` increment (`0.x`) signals significant new capability or structural change
- `PATCH` increment (`0.x.y`) signals a targeted fix with no structural change
- The version `1.0.0` signals the application is considered production-ready with
  a stable CLI API

---

## What Constitutes a Breaking Change (MAJOR bump)

- Removing an existing CLI command or category (`material`, `project`, etc.)
- Renaming a top-level flag or required argument
- Changing the meaning of an existing argument
- Incompatible SQLite schema changes that require manual data migration
- Removing or renaming environment variables that existing setups depend on
- Changing exit codes for previously-successful operations

---

## What Constitutes a New Feature (MINOR bump)

- Adding a new entity category with full CRUD commands
- Adding a new optional flag to an existing command
- Adding a new `database` maintenance operation
- Adding bulk-create support to a category that lacked it
- Adding an external service integration
- Adding a new subcommand (`get`, `stats`, etc.) to an existing category

---

## What Constitutes a Bug Fix (PATCH bump)

- Fixing incorrect output formatting
- Correcting a filter flag that returned wrong results
- Fixing CSV parsing edge cases
- Correcting error messages
- Fixing a non-crashing exception handler
- Documentation corrections
- Internal refactoring with identical external behavior

---

## Version Location

The version is defined in `pyproject.toml` only:

```toml
[project]
version = "0.3.0"
```

**Do not** duplicate the version in `__init__.py`, `__version__` variables, or
any other file. Always read it from the package metadata if needed at runtime:

```python
from importlib.metadata import version
__version__ = version("riskmanager-cli")
```

---

## Changelog Practice

Maintain a `CHANGELOG.md` at the repository root in [Keep a Changelog](https://keepachangelog.com/)
format:

```markdown
# Changelog

## [Unreleased]

## [0.3.0] - 2025-01-01
### Added
- Manufacturing process risk sub-table and CLI commands
- Alias sub-tables for material, ncrm_library, counterion

### Changed
- Renamed manufacturing_process table to manufacturing_processes
- Removed cqas(JSONB) from manufacturing_processes

### Removed
- project_status and interaction tables (not applicable for single-user app)
```

---

## Release Process

1. Update `version` in `pyproject.toml`
2. Update `CHANGELOG.md` (move Unreleased to new version section)
3. Commit: `chore: bump version to X.Y.Z`
4. Tag: `git tag vX.Y.Z`
5. Push tag: `git push origin vX.Y.Z`
6. Build: `python -m build`
7. Install locally: `pip install dist/riskmanager_cli-X.Y.Z-py3-none-any.whl`

---

## Schema Migration and Version Compatibility

SQLite schema changes are managed with **Alembic** (see `10-persistence-layer.md`).

Rules:
- Every schema change gets an Alembic migration script
- `PATCH` fixes may include additive migrations (new index, optional column)
- `MINOR` features may include additive migrations (new table, new optional column)
- `MAJOR` changes include migrations that alter or drop existing structure
- Never modify a committed migration; always add a new one
- Migration scripts are committed alongside the code change that requires them
