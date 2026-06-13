# CLAUDE.md

See @AGENTS.md for all contributor, architecture, code-quality, and quality-gate
rules. They are mandatory for AI-assisted and human changes alike.

Design rationale for the architecture and schema lives in `blueprint/`
(`00-overview.md`, `01-architecture.md`, `02-data-model.md`, `03-repl-ux.md`).
User-facing usage is documented in `README.md`.

## Environment

The virtual environment lives at `~/.venvs/riskmanager` (outside the repo).
Always run tooling through it — never the system Python:

```bash
~/.venvs/riskmanager/bin/python -m ruff check src/ tests/
~/.venvs/riskmanager/bin/python -m pylint src/riskmanager_cli/
~/.venvs/riskmanager/bin/python -m mypy src/riskmanager_cli/
~/.venvs/riskmanager/bin/python -m pytest tests/ -x
```
