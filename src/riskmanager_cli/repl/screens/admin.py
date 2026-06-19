"""The admin screen: CSV import and database maintenance actions.

:class:`AdminScreen` renders the admin landing page and services the ``^A``
action chooser plus the ``/admin import``/``/admin db`` commands. Because
``/admin <args>`` is reachable from any screen (the dispatcher routes it here as a
global command), the command handlers are self-contained and depend only on the
shared application state via ``self.app``.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID

from ...operations.counterion_operations import list_counterions, update_counterion
from ...operations.material_operations import (
    bulk_import_materials,
    list_materials,
    update_material,
)
from ...operations.ncrm_library_operations import (
    list_ncrm_library,
    update_ncrm_library_entry,
)
from ...operations.smiles_operations import canonicalize_smiles
from ...repl_engine.forms import FieldSpec
from ...schema.update import CounterionUpdate, MaterialUpdate, NcrmLibraryUpdate
from ...utils.parsing import split_aliases
from ..form_fields import BOOL_OPTIONS, as_bool
from ..hotkeys import CTRL_A
from ..renderers.admin_renderer import render_admin_screen
from .base import AppScreen
from .library_subsections import LIBRARY_DESCRIPTORS, LibraryDescriptor, LibrarySubsection
from .specs import SCREEN_SPECS


class AdminAction(str, Enum):
    """The three top-level admin actions offered by the ``^A`` chooser."""

    IMPORT = "import"
    ANALYZE = "analyze"
    CANONICALIZE = "canonicalize"


@dataclass(frozen=True)
class _ImportOptions:
    """Parsed ``/admin import`` boolean flags."""

    dry_run: bool = False
    skip_errors: bool = False

    @classmethod
    def from_tokens(cls, tokens: list[str]) -> _ImportOptions:
        """Read ``--dry-run`` / ``--skip-errors`` from the trailing *tokens*."""
        return cls(dry_run="--dry-run" in tokens, skip_errors="--skip-errors" in tokens)


@dataclass(frozen=True)
class _DbOptions:
    """Parsed ``/admin db`` boolean flags."""

    ncrm_only: bool = False
    dry_run: bool = False

    @classmethod
    def from_tokens(cls, tokens: list[str]) -> _DbOptions:
        """Read ``--ncrm`` / ``--dry-run`` from the trailing *tokens*."""
        return cls(ncrm_only="--ncrm" in tokens, dry_run="--dry-run" in tokens)


class AdminScreen(AppScreen):
    """The admin track: CSV import and database analyze/canonicalize actions."""

    key = "admin"
    spec = SCREEN_SPECS["admin"]

    async def render(self) -> list[str]:
        """Render the admin landing page."""
        return render_admin_screen()

    async def run_command(self, verb: str, args: list[str]) -> list[str] | str | None:
        """Dispatch ``/admin import`` / ``/admin db`` (reachable from any screen)."""
        admin_args = args if verb == "/admin" else [verb.removeprefix("/admin"), *args]
        if not admin_args:
            return render_admin_screen()
        if admin_args[0] == "import" and len(admin_args) >= 3:
            return await self._admin_import(admin_args[1:])
        if admin_args[0] == "db" and len(admin_args) >= 2:
            return await self._admin_db(admin_args[1:])
        return ["Usage: /admin import <type> <file.csv> | /admin db <analyze|canonicalize>"]

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Open the admin action chooser on ``^A``."""
        if key_text == CTRL_A:
            return self._start_admin_action_chooser()
        return None

    def _start_admin_action_chooser(self) -> list[str]:
        """Open the top-level admin action chooser (import/analyze/canonicalize)."""
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "action",
                    field_type="select",
                    options=[
                        ("import CSV", AdminAction.IMPORT.value),
                        ("analyze database", AdminAction.ANALYZE.value),
                        ("canonicalize SMILES", AdminAction.CANONICALIZE.value),
                    ],
                )
            ],
            lambda **payload: self._admin_action_dispatch(payload["action"]),
        )

    async def _admin_action_dispatch(self, action: str) -> list[str]:
        """Open the follow-up form for the chosen admin *action*."""
        forms: dict[AdminAction, Callable[[], list[str]]] = {
            AdminAction.IMPORT: self._import_form,
            AdminAction.ANALYZE: self._analyze_form,
            AdminAction.CANONICALIZE: self._canonicalize_form,
        }
        try:
            key = AdminAction(action)
        except ValueError:
            key = AdminAction.CANONICALIZE
        return forms[key]()

    def _import_form(self) -> list[str]:
        """Open the CSV import form (type/file/dry-run/skip-errors)."""
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "type",
                    field_type="select",
                    options=[
                        ("materials", "materials"),
                        ("ncrm", "ncrm"),
                        ("counterions", "counterions"),
                    ],
                ),
                FieldSpec("file"),
                FieldSpec("dry_run", field_type="select", options=BOOL_OPTIONS, default="false"),
                FieldSpec(
                    "skip_errors", field_type="select", options=BOOL_OPTIONS, default="false"
                ),
            ],
            lambda **payload: self._admin_import_from_prompt(payload),
            title="Import CSV",
        )

    def _analyze_form(self) -> list[str]:
        """Open the analyze-scope chooser (all / NCRM-only)."""
        return self.app.modal.start_prompt(
            [self._scope_field()],
            lambda **payload: self._admin_db(
                ["analyze", *(["--ncrm"] if payload["scope"] == "ncrm" else [])]
            ),
        )

    def _canonicalize_form(self) -> list[str]:
        """Open the canonicalize-scope/dry-run chooser."""
        return self.app.modal.start_prompt(
            [
                self._scope_field(),
                FieldSpec("dry_run", field_type="select", options=BOOL_OPTIONS, default="false"),
            ],
            lambda **payload: self._admin_db(
                [
                    "canonicalize",
                    *(["--ncrm"] if payload["scope"] == "ncrm" else []),
                    *(["--dry-run"] if as_bool(payload["dry_run"]) else []),
                ]
            ),
        )

    @staticmethod
    def _scope_field() -> FieldSpec:
        """Return the all/NCRM-only scope select field shared by the db actions."""
        return FieldSpec(
            "scope", field_type="select", options=[("all", "all"), ("ncrm only", "ncrm")]
        )

    async def _admin_import_from_prompt(self, payload: dict[str, str | None]) -> list[str]:
        """Turn the import form's *payload* into CLI-style args and run the import."""
        args = [payload.get("type") or "", payload.get("file") or ""]
        if as_bool(payload.get("dry_run")):
            args.append("--dry-run")
        if as_bool(payload.get("skip_errors")):
            args.append("--skip-errors")
        return await self._admin_import(args)

    async def _admin_import(self, args: list[str]) -> list[str]:
        """Import a CSV of *type* from a file path, honouring dry-run/skip-errors."""
        import_type = args[0].lower()
        file_path = Path(args[1]).expanduser()
        options = _ImportOptions.from_tokens(args[2:])
        if not file_path.exists():
            return [f"File not found: {file_path}"]
        content = file_path.read_text(encoding="utf-8")
        if import_type == "materials":
            counts = await bulk_import_materials(
                content,
                self.app.env,
                skip_errors=options.skip_errors,
                dry_run=options.dry_run,
            )
            created = counts["created"]
            skipped = counts["skipped"]
            errors = counts["errors"]
            return [f"materials import: created={created} skipped={skipped} errors={errors}"]
        return await self._admin_simple_import(import_type, content, options)

    async def _admin_simple_import(
        self, import_type: str, content: str, options: _ImportOptions
    ) -> list[str]:
        """Import NCRM/counterion rows one at a time, counting created/error rows."""
        try:
            subsection = LibrarySubsection(import_type)
        except ValueError:
            subsection = None
        if subsection not in (LibrarySubsection.NCRM, LibrarySubsection.COUNTERIONS):
            return ["Supported admin imports: materials, ncrm, counterions"]
        descriptor = LIBRARY_DESCRIPTORS[subsection]

        created = 0
        errors = 0
        for row in csv.DictReader(StringIO(content)):
            if options.dry_run:
                created += 1
                continue
            try:
                succeeded = await self._import_row(row, descriptor)
            except Exception:  # pylint: disable=broad-exception-caught  # one bad row must not abort the import
                succeeded = False
            if succeeded:
                created += 1
            else:
                errors += 1
                if not options.skip_errors:
                    break
        return [
            f"{import_type} import: created={created} errors={errors} dry_run={options.dry_run}"
        ]

    async def _import_row(self, row: dict[str, str], descriptor: LibraryDescriptor) -> bool:
        """Create one library entry plus its ``;``-separated aliases; ``False`` on failure.

        Driven by the subsection *descriptor* so NCRM and counterion imports share
        one row handler (see :mod:`.library_subsections`).
        """
        result = await descriptor.create_fn(
            descriptor.create_schema(
                name=(row.get("name") or "").strip(),
                display_name=(row.get("display_name") or "").strip() or None,
                interpret_chemically=(
                    (row.get("interpret_chemically") or "false").strip().lower() == "true"
                ),
                smiles=(row.get("smiles") or "").strip() or None,
            ),
            self.app.env,
        )
        if result is None:
            return False
        for alias in split_aliases((row.get("aliases") or "").strip()):
            await descriptor.alias_add_fn(
                descriptor.alias_factory(UUID(str(result.id)), alias), self.app.env
            )
        return True

    async def _admin_db(self, args: list[str]) -> list[str]:
        """Run a database maintenance action (analyze or canonicalize)."""
        options = _DbOptions.from_tokens(args[1:])
        try:
            action = AdminAction(args[0].lower())
        except ValueError:
            action = None
        if action is AdminAction.ANALYZE:
            return await self._admin_db_analyze(options.ncrm_only)
        if action is AdminAction.CANONICALIZE:
            return await self._admin_db_canonicalize(
                ncrm_only=options.ncrm_only, dry_run=options.dry_run
            )
        return ["Usage: /admin db analyze [--ncrm] | /admin db canonicalize [--dry-run] [--ncrm]"]

    async def _admin_db_analyze(self, ncrm_only: bool) -> list[str]:
        """Report row counts (and SMILES coverage for the NCRM-only scope)."""
        if ncrm_only:
            items = await list_ncrm_library(self.app.env)
            with_smiles = sum(1 for item in items if item.smiles)
            return [f"NCRM rows: {len(items)}", f"With SMILES: {with_smiles}"]
        materials = await list_materials(self.app.env)
        counterions = await list_counterions(self.app.env)
        ncrms = await list_ncrm_library(self.app.env)
        return [
            f"Materials: {len(materials)}",
            f"Counterions: {len(counterions)}",
            f"NCRM rows: {len(ncrms)}",
        ]

    async def _admin_db_canonicalize(self, *, ncrm_only: bool, dry_run: bool) -> list[str]:
        """Canonicalize stored SMILES across the chosen scope, counting updates."""
        updated = 0
        if ncrm_only:
            items = await list_ncrm_library(self.app.env)
            for item in items:
                updated += await self._canonicalize_ncrm(item, dry_run)
            return [f"NCRM canonicalized: {updated}", f"Dry run: {dry_run}"]
        for material in await list_materials(self.app.env):
            if material.smiles:
                canonical = canonicalize_smiles(material.smiles)
                if canonical and canonical != material.smiles:
                    updated += 1
                    if not dry_run:
                        await update_material(
                            UUID(str(material.id)), MaterialUpdate(smiles=canonical), self.app.env
                        )
        for counterion in await list_counterions(self.app.env):
            if counterion.smiles:
                canonical = canonicalize_smiles(counterion.smiles)
                if canonical and canonical != counterion.smiles:
                    updated += 1
                    if not dry_run:
                        await update_counterion(
                            UUID(str(counterion.id)),
                            CounterionUpdate(smiles=canonical),
                            self.app.env,
                        )
        for item in await list_ncrm_library(self.app.env):
            updated += await self._canonicalize_ncrm(item, dry_run)
        return [f"Entries canonicalized: {updated}", f"Dry run: {dry_run}"]

    async def _canonicalize_ncrm(self, item: Any, dry_run: bool) -> int:
        """Canonicalize one NCRM entry's SMILES; return 1 if it changed, else 0."""
        if not item.smiles:
            return 0
        canonical = canonicalize_smiles(item.smiles)
        if not canonical or canonical == item.smiles:
            return 0
        if not dry_run:
            await update_ncrm_library_entry(
                UUID(str(item.id)),
                NcrmLibraryUpdate(smiles=canonical),
                self.app.env,
            )
        return 1
