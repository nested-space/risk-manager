"""
SMILES validation, canonicalization, and auto-detection operations.

Delegates the RDKit-backed work (validation, canonicalization) to the
``dmta_cli`` library so the cheminformatics logic lives in one place. The
project-specific :func:`detect_search_type` heuristic (not part of the library)
stays here.

Why this exists:
    SMILES handling is used in material, NCRM, and counterion operations, and
    in the admin ``/admin db canonicalize`` command. Centralising it here means
    the rest of the operations layer imports a simple bool/str API and does not
    need to know which library performs the parsing.
"""

import dmta_cli


def is_valid_smiles(smiles: str) -> bool:
    """Return ``True`` if *smiles* is a valid, parseable SMILES string.

    Args:
        smiles: SMILES string to validate.

    Returns:
        ``True`` if valid; ``False`` otherwise (including empty input).
    """
    return dmta_cli.is_valid(smiles)


def canonicalize_smiles(smiles: str) -> str | None:
    """Return the canonical form of *smiles*, or ``None`` on failure.

    Args:
        smiles: SMILES string to canonicalize.

    Returns:
        The canonical SMILES string, or ``None`` if invalid/empty.
    """
    return dmta_cli.canonicalize(smiles)


def is_canonical_smiles(smiles: str) -> bool:
    """Return ``True`` if *smiles* is already in canonical form.

    Args:
        smiles: SMILES string to check.

    Returns:
        ``True`` if *smiles* == ``canonicalize_smiles(smiles)``; ``False``
        if non-canonical or invalid.
    """
    canonical = canonicalize_smiles(smiles)
    return canonical is not None and canonical == smiles


def detect_search_type(search_value: str) -> str:
    """Infer whether *search_value* is a UUID, SMILES, or name string.

    Used by update-by-search and delete-by-search operations to avoid
    requiring the caller to specify the identifier type explicitly.

    Args:
        search_value: An arbitrary user-supplied identifier string.

    Returns:
        ``"id"`` if *search_value* looks like a UUID4 (32–36 hex chars with
        optional dashes); ``"smiles"`` if it contains chemistry-specific
        characters (``=``, ``(``, ``[``); ``"name"`` otherwise.
    """
    import re  # pylint: disable=import-outside-toplevel

    uuid_pattern = r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$"
    if re.match(uuid_pattern, search_value, re.IGNORECASE):
        return "id"
    smiles_chars = {"=", "(", ")", "[", "]", "@", "#", "+", "-"}
    if any(ch in search_value for ch in smiles_chars):
        return "smiles"
    return "name"
