"""Tracerfy data provider — connects to the Tracerfy MCP server to fetch
high-value new-construction anchors and nearby candidate parcels.

Replaces the ATTOM placeholder.  The connection uses the Model Context
Protocol (Streamable HTTP transport) so the backend acts as a lightweight MCP
client that calls Tracerfy's lead-builder tools.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from app.geo import haversine_ft
from app.models import AnchorHome, Parcel, Provenance
from app.providers.attom import MissingCredentialsError
from app.providers.mcp_client import MCPClient

logger = logging.getLogger(__name__)

MCP_URL_TEMPLATE = "https://mcp.tracerfy.com/u/{token}/mcp"

# Market ID → Tracerfy geography selector (lead-builder ``geography`` param).
MARKET_GEOGRAPHY: dict[str, dict] = {
    "miami-dade-fl": {"mode": "counties", "counties": ["Miami-Dade County, FL"]},
}

# Broad filters for the candidate-parcel fetch.  The pipeline applies its own
# value / year cutoffs afterwards, so these just keep the result set focused on
# the older, lower-value stock the pipeline is interested in.
_PARCEL_FILTERS = {"value_max": 5_000_000, "year_built_max": 2000}

_POLL_INTERVAL = 2.0
_POLL_MAX_ATTEMPTS = 60


class TracerfyProvider:
    """Production data source backed by the Tracerfy MCP server.

    Implements both ``ListingProvider`` and ``ParcelProvider``.
    """

    name = "tracerfy"

    def __init__(self, token: str | None = None) -> None:
        token = token or os.getenv("TRACERFY_API_KEY")
        if not token:
            raise MissingCredentialsError(
                "TRACERFY_API_KEY is not set. Generate a connector token in your "
                "Tracerfy profile → Connect via MCP and add it as TRACERFY_API_KEY."
            )
        self._client = MCPClient(MCP_URL_TEMPLATE.format(token=token))
        self._parcel_cache: dict[str, list[Parcel]] = {}

    # -- helpers ------------------------------------------------------------

    def _geography(self, market: str) -> dict:
        geo = MARKET_GEOGRAPHY.get(market)
        if not geo:
            raise ValueError(
                f"No Tracerfy geography mapping for market '{market}'. "
                f"Add it to MARKET_GEOGRAPHY in app/providers/tracerfy.py."
            )
        return geo

    def _build_lead_list(
        self,
        geography: dict,
        filters: dict,
        count: int = 500,
        name: str = "UltraSpec Radar",
    ) -> list[dict]:
        """Execute a lead list, poll to completion, and return all rows."""
        logger.info("Executing Tracerfy lead list: %s, filters=%s, count=%d", name, filters, count)
        result = self._client.call_tool("execute_lead_list", {
            "geography": geography,
            "requested_count": count,
            "filter_overrides": filters,
            "name": name,
        })
        lead_list_id = self._extract_id(result)

        for _ in range(_POLL_MAX_ATTEMPTS):
            status = self._client.call_tool("get_lead_list_status", {"lead_list_id": lead_list_id})
            if isinstance(status, dict) and status.get("status") in ("complete", "completed", "done"):
                break
            time.sleep(_POLL_INTERVAL)
        else:
            raise RuntimeError(f"Tracerfy lead list {lead_list_id} did not complete in time.")

        rows: list[dict] = []
        page = 1
        while True:
            page_result = self._client.call_tool("get_lead_list_rows", {
                "lead_list_id": lead_list_id,
                "page": page,
                "per_page": 100,
            })
            if not isinstance(page_result, dict):
                break
            rows.extend(page_result.get("rows", []))
            total_pages = page_result.get("total_pages", page)
            if page >= total_pages:
                break
            page += 1
        logger.info("Tracerfy lead list %s returned %d rows", lead_list_id, len(rows))
        return rows

    @staticmethod
    def _extract_id(result: object) -> int:
        if isinstance(result, dict):
            for key in ("lead_list_id", "id"):
                if key in result:
                    return int(result[key])
        raise RuntimeError(f"Could not extract lead list id from Tracerfy response: {result}")

    # -- ListingProvider ----------------------------------------------------

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        geography = self._geography(market)
        filters = {"value_min": min_price, "year_built_min": min_year_built}
        rows = self._build_lead_list(geography, filters, count=500, name="UltraSpec Anchors")

        anchors: list[AnchorHome] = []
        for row in rows:
            lat = row.get("latitude")
            lon = row.get("longitude")
            if lat is None or lon is None:
                continue
            apn = row.get("apn")
            anchors.append(AnchorHome(
                id=apn or f"tracerfy-{row['address']}",
                address=row.get("address", ""),
                city=row.get("city", ""),
                state=row.get("state", ""),
                zip_code=row.get("zip_code", ""),
                lat=float(lat),
                lon=float(lon),
                price=float(row.get("estimated_value") or row.get("last_sale_price") or 0.0),
                status=self._derive_status(row),
                year_built=row.get("year_built") or 0,
                parcel_id=apn,
                provenance=Provenance(
                    source="tracerfy",
                    source_url=None,
                    retrieved_at=datetime.now(timezone.utc),
                ),
            ))
        return anchors

    @staticmethod
    def _derive_status(row: dict) -> str:
        if row.get("mls_sold"):
            return "sold"
        if row.get("mls_pending"):
            return "under_contract"
        if row.get("mls_active"):
            return "listed"
        return "sold"

    # -- ParcelProvider -----------------------------------------------------

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        if market not in self._parcel_cache:
            geography = self._geography(market)
            rows = self._build_lead_list(geography, _PARCEL_FILTERS, count=500, name="UltraSpec Candidates")
            self._parcel_cache[market] = [self._row_to_parcel(row) for row in rows if self._has_coords(row)]

        return [
            p for p in self._parcel_cache[market]
            if haversine_ft(lat, lon, p.lat, p.lon) <= radius_ft
        ]

    @staticmethod
    def _has_coords(row: dict) -> bool:
        return row.get("latitude") is not None and row.get("longitude") is not None

    @staticmethod
    def _row_to_parcel(row: dict) -> Parcel:
        apn = row.get("apn")
        owner_parts = [row.get("owner_1_first_name"), row.get("owner_1_last_name")]
        owner_name = " ".join(p for p in owner_parts if p) or None
        return Parcel(
            parcel_id=apn or f"tracerfy-{row['address']}",
            address=row.get("address", ""),
            city=row.get("city", ""),
            state=row.get("state", ""),
            zip_code=row.get("zip_code", ""),
            lat=float(row["latitude"]),
            lon=float(row["longitude"]),
            year_built=row.get("year_built"),
            lot_size_sqft=row.get("lot_size_sqft"),
            estimated_value=row.get("estimated_value"),
            owner_name=owner_name,
            provenance=Provenance(
                source="tracerfy",
                source_url=None,
                retrieved_at=datetime.now(timezone.utc),
            ),
        )
