"""The command dispatcher must satisfy the engine's controller contract.

This guards the seam between the application-agnostic engine and the application:
if a method the loop drives is renamed or dropped from ``CommandDispatcher``, this
test fails before the loop breaks at runtime.
"""

import pytest

from riskmanager_cli.repl.commands import CommandDispatcher
from riskmanager_cli.repl.context import ContextManager
from riskmanager_cli.repl_engine.controller import ReplController


class _StubScreen:
    """Minimal screen stand-in; the dispatcher only stores it at construction."""

    width = 80
    output_height = 40

    @staticmethod
    def dim(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text

    @staticmethod
    def bold(text: str) -> str:
        """Return *text* unchanged (no terminal styling under test)."""
        return text


@pytest.mark.unit
def test_command_dispatcher_satisfies_repl_controller() -> None:
    """The dispatcher exposes every member the engine's controller protocol names."""
    dispatcher = CommandDispatcher(ContextManager(), None, _StubScreen(), None)  # type: ignore[arg-type]
    assert isinstance(dispatcher, ReplController)
