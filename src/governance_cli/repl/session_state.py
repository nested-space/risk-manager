"""JSON-backed persistence for lightweight REPL session state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from ..config.settings import get_session_path

_CONTEXT_KEYS: tuple[str, ...] = (
    "track",
    "project_id",
    "process_id",
    "stage_id",
    "component_id",
)


@dataclass
class SessionState:
    """Persist recent navigation state between REPL launches.

    Attributes:
        path: JSON file path for persisted state.
        recent_projects: Most recently visited project UUIDs, newest first.
        recent_routes: Per-project recent manufacturing-process UUIDs.
        last_context: Last active navigation identifiers.
        version: Session file schema version.
    """

    VERSION: ClassVar[int] = 1

    path: Path = field(default_factory=get_session_path)
    recent_projects: list[str] = field(default_factory=list)
    recent_routes: dict[str, list[str]] = field(default_factory=dict)
    last_context: dict[str, str | None] = field(
        default_factory=lambda: {key: None for key in _CONTEXT_KEYS}
    )
    version: int = VERSION

    @classmethod
    def load(cls, path: Path | None = None) -> SessionState:
        """Load persisted session state.

        Invalid or unreadable JSON is treated as an empty session state.

        Args:
            path: Optional override for the session JSON path.

        Returns:
            A populated :class:`SessionState` instance.
        """
        resolved_path = (path or get_session_path()).expanduser().resolve()
        try:
            raw = json.loads(resolved_path.read_text(encoding="utf-8"))
            last_context_raw = raw.get("last_context", {})
            return cls(
                path=resolved_path,
                recent_projects=cls._normalize_ids(raw.get("recent_projects", []), cap=5),
                recent_routes=cls._normalize_routes(raw.get("recent_routes", {})),
                last_context={
                    key: cls._normalize_optional_text(last_context_raw.get(key))
                    for key in _CONTEXT_KEYS
                },
                version=int(raw.get("version", cls.VERSION)),
            )
        except Exception:
            return cls(path=resolved_path)

    def save(self) -> None:
        """Persist session state to disk.

        File-system failures are intentionally ignored so that the REPL never
        crashes because history could not be saved.
        """
        payload = {
            "version": self.version,
            "recent_projects": self.recent_projects[:5],
            "recent_routes": {
                project_id: routes[:3]
                for project_id, routes in self.recent_routes.items()
                if routes
            },
            "last_context": {key: self.last_context.get(key) for key in _CONTEXT_KEYS},
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            return

    def push_project(self, project_id: str) -> None:
        """Record *project_id* as the most recently visited project.

        Args:
            project_id: Project UUID string.
        """
        self.recent_projects = [
            project_id,
            *[item for item in self.recent_projects if item != project_id],
        ][:5]

    def push_route(self, project_id: str, process_id: str) -> None:
        """Record *process_id* as recently visited within *project_id*.

        Args:
            project_id: Project UUID string.
            process_id: Manufacturing process UUID string.
        """
        existing = self.recent_routes.get(project_id, [])
        self.recent_routes[project_id] = [
            process_id,
            *[item for item in existing if item != process_id],
        ][:3]

    def update_context(self, **kwargs: str | None) -> None:
        """Update remembered navigation context fields.

        Unsupported keys are ignored.

        Args:
            **kwargs: Context key/value pairs to update.
        """
        for key, value in kwargs.items():
            if key in self.last_context:
                self.last_context[key] = value

    @staticmethod
    def _normalize_ids(values: object, cap: int) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            text = SessionState._normalize_optional_text(value)
            if text is not None and text not in normalized:
                normalized.append(text)
            if len(normalized) >= cap:
                break
        return normalized

    @staticmethod
    def _normalize_routes(values: object) -> dict[str, list[str]]:
        if not isinstance(values, dict):
            return {}
        normalized: dict[str, list[str]] = {}
        for key, route_values in values.items():
            project_id = SessionState._normalize_optional_text(key)
            if project_id is None:
                continue
            routes = SessionState._normalize_ids(route_values, cap=3)
            if routes:
                normalized[project_id] = routes
        return normalized

    @staticmethod
    def _normalize_optional_text(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None
