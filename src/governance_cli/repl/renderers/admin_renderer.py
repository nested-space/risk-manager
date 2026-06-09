"""Static renderer for the admin command reference screen."""

from __future__ import annotations


def render_admin_screen() -> list[str]:
    """Return display lines for the Admin sub-mode."""
    return [
        "Admin",
        "",
        "Import commands",
        "  /admin import materials <file.csv> [--dry-run] [--skip-errors]",
        "  /admin import ncrm <file.csv> [--dry-run] [--skip-errors]",
        "  /admin import counterions <file.csv> [--dry-run] [--skip-errors]",
        "",
        "Database commands",
        "  /admin db analyze [--ncrm]",
        "  /admin db canonicalize [--dry-run] [--ncrm]",
    ]
