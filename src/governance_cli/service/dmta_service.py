"""DMTA compound-registry HTTP client.

:class:`DmtaService` wraps the optional DMTA REST API using an ``httpx``
async client.  All methods return ``None`` (rather than raising) when the
service is unavailable or the compound is not found, so the caller can treat
enrichment as a best-effort operation.

Configuration is done via the constructor; the caller is responsible for
reading environment variables before instantiation (see
:func:`~governance_cli.operations.dmta_operations.enrich_material_with_dmta`).
"""

from __future__ import annotations

import logging

import httpx

from .smiles_comparison_result import SmilesComparisonResult

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0


class DmtaService:
    """Async HTTP client for the DMTA compound registry.

    All public methods are ``async def`` and open their own ``httpx`` session.
    They return ``None`` on any HTTP or network error rather than propagating
    exceptions, keeping enrichment genuinely optional.

    Args:
        api_url: Base URL of the DMTA REST API (e.g. ``"https://dmta.example.com/api"``).
        api_key: Optional API bearer token.  When supplied it is sent in the
            ``Authorization: Bearer <key>`` header.
        timeout: Request timeout in seconds.  Defaults to
            :data:`_DEFAULT_TIMEOUT_SECONDS`.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialise the DMTA service client."""
        self._base_url = api_url.rstrip("/")
        self._headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_by_name(self, name: str) -> SmilesComparisonResult | None:
        """Look up a compound by its preferred name.

        Args:
            name: The compound name to search for (exact match).

        Returns:
            A :class:`~governance_cli.service.smiles_comparison_result.SmilesComparisonResult`
            if the compound was found, or ``None`` on error / not found.
        """
        return await self._get("/compounds/search", params={"name": name})

    async def search_by_smiles(self, smiles: str) -> SmilesComparisonResult | None:
        """Look up a compound by its SMILES string.

        Args:
            smiles: SMILES string to look up (exact canonical match expected).

        Returns:
            A :class:`~governance_cli.service.smiles_comparison_result.SmilesComparisonResult`
            if the compound was found, or ``None`` on error / not found.
        """
        return await self._get("/compounds/search", params={"smiles": smiles})

    async def get_by_id(self, registry_id: str) -> SmilesComparisonResult | None:
        """Fetch a compound record by its registry identifier.

        Args:
            registry_id: The DMTA internal compound ID.

        Returns:
            A :class:`~governance_cli.service.smiles_comparison_result.SmilesComparisonResult`
            if the compound was found, or ``None`` on error / not found.
        """
        return await self._get(f"/compounds/{registry_id}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> SmilesComparisonResult | None:
        """Execute a GET request and parse the response.

        Args:
            path: API path relative to ``_base_url`` (must start with ``/``).
            params: Optional query parameters.

        Returns:
            A :class:`SmilesComparisonResult` on success, or ``None``.
        """
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
            ) as client:
                response = await client.get(url, params=params)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                payload: dict[str, object] = response.json()
                return SmilesComparisonResult.from_api_response(payload)
        except httpx.HTTPStatusError as exc:
            logger.warning("DMTA HTTP error %s for %s: %s", exc.response.status_code, url, exc)
            return None
        except httpx.RequestError as exc:
            logger.warning("DMTA network error for %s: %s", url, exc)
            return None
        except Exception as exc:  # pylint: disable=broad-except  # enrichment must never propagate
            logger.warning("DMTA unexpected error for %s: %s", url, exc)
            return None
