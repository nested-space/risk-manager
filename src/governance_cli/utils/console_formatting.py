"""
Console output formatting helpers for the operations layer.

Provides coloured terminal output functions used throughout
``operations/*_operations.py``. These are the **only** direct ``print()``
calls permitted outside the REPL layer. REPL modules must use
``ScreenManager.draw_*()`` instead.

Why this exists:
    Centralising terminal colour codes here means that the colour scheme can
    be changed in one place, and that operations code can be tested by
    redirecting stdout without coupling to blessed terminal objects.
"""

import colorama
from colorama import Fore, Style

colorama.init(autoreset=True)


def print_error(message: str) -> None:
    """Print a red error message to stdout.

    Use in the operations layer when an exception is caught and the operation
    cannot complete. The operations function should return ``None`` or ``[]``
    after calling this.

    Args:
        message: Human-readable error description.
    """
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")


def print_warning(message: str) -> None:
    """Print a yellow warning message to stdout.

    Use for non-fatal issues such as skipped rows during bulk import.

    Args:
        message: Human-readable warning description.
    """
    print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")


def print_info(message: str) -> None:
    """Print a cyan informational message to stdout.

    Use for status updates such as dry-run previews or progress feedback.

    Args:
        message: Human-readable informational text.
    """
    print(f"{Fore.CYAN}ℹ {message}{Style.RESET_ALL}")


def print_success(message: str) -> None:
    """Print a green success message to stdout.

    Use to confirm that an operation completed successfully.

    Args:
        message: Human-readable confirmation text.
    """
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")


def print_key_value(key: str, value: str) -> None:
    """Print a key–value pair with the key highlighted in white.

    Use for structured diagnostic output (e.g. configuration display).

    Args:
        key: Label string.
        value: Associated value string.
    """
    print(f"{Style.BRIGHT}{key}:{Style.RESET_ALL} {value}")
