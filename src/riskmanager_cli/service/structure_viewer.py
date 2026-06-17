"""Render molecular structures from SMILES and open them in an image viewer.

This module owns the two OS-facing concerns of the structure-display feature:
rendering a SMILES string to a cached PNG (via the ``dmta_cli`` RDKit wrapper)
and launching a system image viewer to show it. It performs no terminal output
and touches no database, so it is exercised in isolation by unit tests.

Why this exists:
    The REPL layer must not shell out or print directly. Centralising the
    render-and-launch logic here gives the command layer a single call that
    returns a :class:`StructureResult`, which it maps to a status notice.
"""

import hashlib
import os
import shutil
import subprocess
from enum import Enum, auto

import dmta_cli

from ..config.settings import get_structure_cache_dir

# Probed in order; the first one found on ``PATH`` is used unless the
# ``RMGR_IMAGE_VIEWER`` environment variable overrides the choice.
_VIEWERS = ("feh", "xdg-open", "display")


class StructureResult(Enum):
    """Outcome of a :func:`show_structure` call.

    Attributes:
        OK: Image rendered (or already cached) and the viewer was launched.
        RENDER_FAILED: SMILES could not be rendered (invalid or backend error).
        NO_VIEWER: No image viewer is installed/configured.
        LAUNCH_FAILED: A viewer was found but could not be spawned.
    """

    OK = auto()
    RENDER_FAILED = auto()
    NO_VIEWER = auto()
    LAUNCH_FAILED = auto()


def find_viewer() -> str | None:
    """Return the image-viewer command to use, or ``None`` if none is available.

    Honours the ``RMGR_IMAGE_VIEWER`` environment variable when set; otherwise
    returns the first of :data:`_VIEWERS` resolvable on ``PATH``.

    Returns:
        An executable name/path runnable via :class:`subprocess.Popen`, or
        ``None`` when nothing suitable is found.
    """
    override = os.getenv("RMGR_IMAGE_VIEWER")
    if override:
        return override
    for viewer in _VIEWERS:
        if shutil.which(viewer):
            return viewer
    return None


def show_structure(smiles: str, *, width: int = 400, height: int = 300) -> StructureResult:
    """Render *smiles* to a cached PNG and open it in a system image viewer.

    The PNG is cached under :func:`get_structure_cache_dir` keyed by the SHA-256
    of *smiles*, so repeat views of the same structure skip re-rendering. The
    viewer is launched detached (its own session) so it never blocks or disturbs
    the REPL's terminal.

    Why ``LAUNCH_FAILED`` is narrow:
        ``Popen`` succeeds as soon as the viewer process starts. If the viewer
        later exits on its own (for example, no ``$DISPLAY`` is available), that
        is not reported here; only a spawn-time :class:`OSError` (missing or
        unrunnable binary) yields ``LAUNCH_FAILED``.

    Args:
        smiles: SMILES string to render. Assumed non-empty; the caller handles
            the "no SMILES" case so it can name the entity in its message.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        A :class:`StructureResult` describing the outcome.
    """
    cache_path = get_structure_cache_dir() / f"{hashlib.sha256(smiles.encode()).hexdigest()}.png"
    if not cache_path.exists():
        try:
            dmta_cli.render(smiles, fmt="png", out_path=cache_path, width=width, height=height)
        except Exception:  # pylint: disable=broad-except  # any RDKit/render error → caller notice
            return StructureResult.RENDER_FAILED

    viewer = find_viewer()
    if viewer is None:
        return StructureResult.NO_VIEWER

    try:
        subprocess.Popen(  # pylint: disable=consider-using-with  # detached viewer; not awaited
            [viewer, str(cache_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return StructureResult.LAUNCH_FAILED
    return StructureResult.OK
