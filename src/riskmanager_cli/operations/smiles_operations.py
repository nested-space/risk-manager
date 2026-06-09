"""
SMILES validation, canonicalization, and auto-detection operations.

Wraps RDKit functions for use in the operations layer. All functions degrade
gracefully when RDKit is unavailable or the SMILES string is invalid: they
return ``None`` or ``False`` rather than raising.

Why this exists:
    SMILES handling is used in material, NCRM, and counterion operations, and
    in the admin ``/admin db canonicalize`` command. Centralising RDKit calls
    here means the rest of the operations layer imports a simple bool/str API
    and does not need to know about RDKit internals.
"""

from ..utils.console_formatting import print_warning


def is_valid_smiles(smiles: str) -> bool:
    """Return ``True`` if *smiles* is a valid, parseable SMILES string.

    Uses RDKit's ``MolFromSmiles`` to attempt parsing. Returns ``False`` if
    parsing fails or if RDKit is unavailable.

    Args:
        smiles: SMILES string to validate.

    Returns:
        ``True`` if valid; ``False`` if invalid or RDKit unavailable.
    """
    try:
        from rdkit import Chem  # pylint: disable=import-outside-toplevel

        mol = Chem.MolFromSmiles(smiles)
        return mol is not None
    except ImportError:
        print_warning("RDKit not available; SMILES validation skipped.")
        return True  # non-blocking: treat as valid when RDKit absent
    except Exception:  # pylint: disable=broad-except
        return False


def canonicalize_smiles(smiles: str) -> str | None:
    """Return the RDKit canonical form of *smiles*, or ``None`` on failure.

    Args:
        smiles: SMILES string to canonicalize.

    Returns:
        The canonical SMILES string, or ``None`` if invalid / RDKit unavailable.
    """
    try:
        from rdkit import Chem  # pylint: disable=import-outside-toplevel

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.MolToSmiles(mol)
    except ImportError:
        print_warning("RDKit not available; returning SMILES unchanged.")
        return smiles
    except Exception:  # pylint: disable=broad-except
        return None


def is_canonical_smiles(smiles: str) -> bool:
    """Return ``True`` if *smiles* is already in canonical RDKit form.

    Args:
        smiles: SMILES string to check.

    Returns:
        ``True`` if *smiles* == ``canonicalize_smiles(smiles)``; ``False``
        if non-canonical, invalid, or RDKit unavailable.
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
