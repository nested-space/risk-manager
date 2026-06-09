"""
DMTA enrichment operations.

Provides async functions that call the optional external DMTA enrichment
service to populate SMILES notation and synonyms for materials. If the
``DMTA_API_URL`` environment variable is not set, enrichment is silently
skipped rather than raising.

Why this exists:
    DMTA enrichment is an optional, external-service-dependent feature.
    Isolating it here allows the rest of the operations layer to call a
    simple ``enrich_material_from_dmta()`` function without knowing whether
    the service is configured.
"""

import os

from ..utils.console_formatting import print_error, print_warning


async def enrich_material_from_dmta(
    material_name: str,
) -> dict[str, str] | None:
    """Fetch SMILES and synonyms for *material_name* from the DMTA service.

    Reads ``DMTA_API_URL`` and ``DMTA_API_KEY`` from the environment. If
    ``DMTA_API_URL`` is not set, logs a warning and returns ``None``.

    Args:
        material_name: The material name to look up in the DMTA service.

    Returns:
        A dict with keys ``"smiles"`` and ``"synonyms"`` if enrichment succeeds;
        ``None`` if the service is unavailable, unconfigured, or returns no data.
    """
    api_url = os.getenv("DMTA_API_URL")
    if not api_url:
        print_warning("DMTA enrichment requested but DMTA_API_URL is not set; skipping.")
        return None

    api_key = os.getenv("DMTA_API_KEY", "")

    try:
        import httpx  # pylint: disable=import-outside-toplevel

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{api_url.rstrip('/')}/materials/search",
                params={"name": material_name},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            if not data:
                return None
            item = data[0] if isinstance(data, list) else data
            return {
                "smiles": item.get("smiles", ""),
                "synonyms": item.get("synonyms", ""),
            }
    except ImportError:
        print_warning("httpx not installed; DMTA enrichment unavailable.")
        return None
    except Exception as exc:  # pylint: disable=broad-except
        print_error(f"DMTA enrichment failed for '{material_name}': {exc}")
        return None
