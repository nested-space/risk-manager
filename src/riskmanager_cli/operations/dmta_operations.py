"""
Compound-name augmentation operations.

Wraps the ``dmta_cli`` library so the rest of the application can resolve a
compound name to a canonical SMILES string plus aliases without importing the
library directly. ``dmta_cli`` tries the optional DMTA registry first (when
``DMTA_API_KEY`` / ``DMTA_BATCH_SEARCH_ENDPOINT`` are configured) and falls back
to PubChem.

Why this exists:
    Name → SMILES/alias resolution is an external-service-dependent feature.
    Isolating it here keeps the REPL and operations layers decoupled from the
    library and gives callers a single, typed entry point.
"""

import dmta_cli
from dmta_cli import ResolveResult

__all__ = ["ResolveResult", "augment_name"]


async def augment_name(name: str) -> ResolveResult:
    """Resolve *name* to a SMILES string and aliases via ``dmta_cli``.

    Tries DMTA first (when configured), then PubChem. Never raises: on any
    failure or miss it returns an unresolved :class:`ResolveResult` (check
    ``.resolved`` / ``.smiles``).

    Args:
        name: The compound name to resolve.

    Returns:
        A :class:`ResolveResult` carrying ``smiles``, ``aliases``, and ``source``.
    """
    return await dmta_cli.aresolve(name)
