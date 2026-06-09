"""Double-Escape handling for safe REPL back-navigation."""

from __future__ import annotations

from time import monotonic
from typing import ClassVar


class EscapeHandler:
    """Require a double Escape press before leaving the current mode."""

    TIMEOUT_SECONDS: ClassVar[float] = 2.0

    def __init__(self) -> None:
        """Initialise the handler in the disarmed state."""
        self._first_esc_time: float | None = None

    def handle_esc(self, in_guided_prompt: bool = False) -> str:
        """Process an Escape keypress.

        Args:
            in_guided_prompt: Whether Escape is currently acting on a guided prompt.

        Returns:
            ``"NAVIGATE_UP"`` on a confirmed second Escape press, otherwise a
            warning string that the caller should display.
        """
        now = monotonic()
        if self._first_esc_time is None or now - self._first_esc_time > self.TIMEOUT_SECONDS:
            self._first_esc_time = now
            action = "cancel this prompt" if in_guided_prompt else "go back"
            return f"Press Esc again within {self.TIMEOUT_SECONDS:.0f}s to {action}."
        self.disarm()
        return "NAVIGATE_UP"

    def is_armed(self) -> bool:
        """Return ``True`` when the first Escape press is still active."""
        return self._first_esc_time is not None

    def disarm(self) -> None:
        """Clear any pending Escape confirmation."""
        self._first_esc_time = None
