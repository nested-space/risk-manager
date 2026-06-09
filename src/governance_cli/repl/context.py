"""Context-stack helpers for REPL navigation and breadcrumb rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextFrame:
    """One navigation frame in the REPL context stack.

    Attributes:
        track: Active top-level mode name.
        project_id: Current project UUID.
        project_name: Current project display name.
        process_id: Current manufacturing process UUID.
        route_label: Current route label such as ``"1.1"``.
        stage_id: Current stage UUID.
        stage_name: Current stage display name.
        component_id: Current component UUID.
        component_name: Current component display name.
        library_sub: Active library subsection.
        risk_scope: Scope label for risk mode.
    """

    track: str
    project_id: str | None = None
    project_name: str | None = None
    process_id: str | None = None
    route_label: str | None = None
    stage_id: str | None = None
    stage_name: str | None = None
    component_id: str | None = None
    component_name: str | None = None
    library_sub: str | None = None
    risk_scope: str | None = None


class ContextManager:
    """Manage the REPL navigation stack."""

    def __init__(self) -> None:
        """Initialise the stack at the home screen."""
        self._stack: list[ContextFrame] = [ContextFrame(track="home")]

    @property
    def current(self) -> ContextFrame:
        """Return the active context frame."""
        return self._stack[-1]

    def push(self, frame: ContextFrame) -> None:
        """Push a new frame onto the stack.

        Args:
            frame: Frame to become current.
        """
        self._stack.append(frame)

    def pop(self) -> ContextFrame | None:
        """Pop the current frame unless already at the root frame.

        Returns:
            The removed frame, or ``None`` if the stack is already at ``home``.
        """
        if len(self._stack) == 1:
            return None
        return self._stack.pop()

    def reset(self) -> None:
        """Reset navigation back to the home frame."""
        self._stack = [ContextFrame(track="home")]

    def breadcrumb(self) -> str:
        """Render the breadcrumb string for the current frame."""
        frame = self.current
        if frame.track == "risk_mode" and len(self._stack) > 1:
            return f"{self._breadcrumb_for_frame(self._stack[-2])}  ›  [ Risks ]"
        return self._breadcrumb_for_frame(frame)

    def mode_label(self) -> str:
        """Return the current mode label for the status bar."""
        return f"MODE: {self.current.track}"

    def _breadcrumb_for_frame(self, frame: ContextFrame) -> str:
        project_name = frame.project_name or "Unknown"
        route_label = frame.route_label or "?"
        stage_name = frame.stage_name or "Unknown"
        component_name = frame.component_name or "Unknown"
        library_sub = frame.library_sub or "select"
        match frame.track:
            case "home":
                return "[ Home ]"
            case "project":
                return f"[ Project: {project_name} ]"
            case "route_select":
                return f"[ Project: {project_name} ]  ›  [ Route ]"
            case "route":
                return f"[ Project: {project_name} ]  ›  [ Route: {route_label} ]"
            case "stage_focus":
                return (
                    f"[ Project: {project_name} ]  ›  [ Route: {route_label} ]  ›  "
                    f"[ Stage: {stage_name} ]"
                )
            case "component_focus":
                return (
                    f"[ Project: {project_name} ]  ›  [ Route: {route_label} ]  ›  "
                    f"[ Component: {component_name} ]"
                )
            case "library":
                return f"[ Library: {library_sub} ]"
            case "admin":
                return "[ Admin ]"
            case _:
                return "[ Home ]"
