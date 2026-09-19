"""Providers backed by the Maricopa County Assessor's live parcel layer.

Paradise Valley, AZ is a town inside Maricopa County; its parcels live on the
county assessor's public ArcGIS server (the same services that power the
assessor's parcel viewer):

    https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0

The layer carries the full tax roll (full cash value, year built, lot size,
owner of record) but stores values/years as comma-formatted strings, so
numeric server-side WHERE filters fail. Instead we bulk-fetch every
"PARADISE VALLEY" residential parcel once (~7k rows, attributes only — the
layer has LATITUDE/LONGITUDE columns), cache it briefly, and do anchor and
radius filtering in memory. Anchors are residential site-built parcels
(PUC 01xx) with full cash value >= threshold and year built >= threshold.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from app.geo import haversine_ft
from app.models import AnchorHome, Parcel, Provenance
from app.providers.miamidade import ProviderUnavailableError

MARKET = "paradise-valley-az"
JURISDICTION = "PARADISE VALLEY"
RESIDENTIAL_PUC_PREFIX = "01"  # assessor property-use codes: 01xx = residential site-built
QUERY_URL = "https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0/query"
SOURCE = "Maricopa County Assessor - Parcels (county GIS)"
SOURCE_PAGE = "https://maps.mcassessor.maricopa.gov/"
PAGE_SIZE = 1000  # the layer's maxRecordCount
CACHE_TTL_SECONDS = 600

OUT_FIELDS = ",".join(
    [
        "APN",
        "PHYSICAL_ADDRESS",
        "PHYSICAL_CITY",
        "PHYSICAL_ZIP",
        "LATITUDE",
        "LONGITUDE",
        "CONST_YEAR",
        "FCV_CUR",
        "LAND_SIZE",
        "OWNER_NAME",
        "PUC",
    ]
)

_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, produce: Callable[[], Any]) -> Any:
    """Short-lived memo so repeated scans spare the county endpoint."""
    hit = _cache.get(key)
    if hit is not None and hit[0] > time.monotonic():
        return hit[1]
    value = produce()
    _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, value)
    return value


def _require_market(market: str) -> None:
    if market != MARKET:
        raise ValueError(f"Maricopa providers only support market '{MARKET}', got '{market}'.")


def _parse_int(value: Any) -> int | None:
    """FCV/CONST_YEAR are comma-formatted strings like '   3,310,300' / '2020'."""
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    return int(text) if text.isdigit() else None


def _paradise_valley_rows(transport: httpx.BaseTransport | None) -> list[dict[str, Any]]:
    """The cached bulk roll — the county endpoint is fetched at most once per TTL."""

    def produce() -> list[dict[str, Any]]:
        return _fetch_paradise_valley_rows(transport)

    return _cached("maricopa:pv-rows", produce)


def _fetch_paradise_valley_rows(transport: httpx.BaseTransport | None) -> list[dict[str, Any]]:
    """All residential Paradise Valley parcels, normalized to typed dicts."""
    rows: list[dict] = []
    offset = 0
    with httpx.Client(timeout=30.0, transport=transport) as client:
        while True:
            request = {
                "where": f"JURISDICTION='{JURISDICTION}'",
                "outFields": OUT_FIELDS,
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "json",
            }
            try:
                response = client.post(QUERY_URL, data=request)
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError(f"Maricopa County GIS request failed: {exc}") from exc
            if response.status_code != 200:
                raise ProviderUnavailableError(
                    f"Maricopa County GIS returned HTTP {response.status_code}."
                )
            payload = response.json()
            if "error" in payload:
                raise ProviderUnavailableError(
                    f"Maricopa County GIS query error: {payload['error'].get('message', payload['error'])}"
                )
            for feature in payload.get("features", []):
                attrs = feature["attributes"]
                if not str(attrs.get("PUC") or "").startswith(RESIDENTIAL_PUC_PREFIX):
                    continue
                if attrs.get("LATITUDE") is None or attrs.get("LONGITUDE") is None:
                    continue
                rows.append(
                    {
                        "parcel_id": str(attrs["APN"]),
                        "address": str(attrs.get("PHYSICAL_ADDRESS") or "").strip(),
                        "city": str(attrs.get("PHYSICAL_CITY") or ""),
                        "zip_code": str(attrs.get("PHYSICAL_ZIP") or ""),
                        "lat": float(attrs["LATITUDE"]),
                        "lon": float(attrs["LONGITUDE"]),
                        "year_built": _parse_int(attrs.get("CONST_YEAR")),
                        "value": _parse_int(attrs.get("FCV_CUR")),
                        "lot_size_sqft": (
                            float(attrs["LAND_SIZE"]) if attrs.get("LAND_SIZE") is not None else None
                        ),
                        "owner_name": (str(attrs["OWNER_NAME"]).strip() if attrs.get("OWNER_NAME") else None),
                    }
                )
            page_size = len(payload.get("features", []))
            if page_size < PAGE_SIZE:
                return rows
            offset += PAGE_SIZE


class MaricopaListingProvider:
    """Anchor homes from the assessor's full cash value roll.

    An anchor is a residential site-built parcel whose full cash value is at
    least `min_price` and whose year built is at least `min_year_built` — the
    assessor's counterpart of "$15M+ new construction".
    """

    name = "maricopa:anchors"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        _require_market(market)

        def produce() -> list[AnchorHome]:
            now = datetime.now(timezone.utc)
            anchors = [
                AnchorHome(
                    id=row["parcel_id"],
                    address=row["address"],
                    city=row["city"],
                    state="AZ",
                    zip_code=row["zip_code"],
                    lat=row["lat"],
                    lon=row["lon"],
                    price=float(row["value"]),
                    status="sold",
                    year_built=row["year_built"],
                    parcel_id=row["parcel_id"],
                    provenance=Provenance(source=SOURCE, source_url=SOURCE_PAGE, retrieved_at=now),
                )
                for row in _paradise_valley_rows(self._transport)
                if row["value"] is not None
                and row["value"] >= min_price
                and row["year_built"] is not None
                and row["year_built"] >= min_year_built
            ]
            anchors.sort(key=lambda a: -a.price)
            return anchors

        return _cached(f"maricopa:anchors:{min_price:.0f}:{int(min_year_built)}", produce)


class MaricopaParcelProvider:
    """Neighboring residential parcels, filtered in memory from the cached roll.

    The pipeline applies value/age/ownership filters downstream.
    """

    name = "maricopa:parcels"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        _require_market(market)

        def produce() -> list[Parcel]:
            now = datetime.now(timezone.utc)
            parcels = []
            for row in _paradise_valley_rows(self._transport):
                if haversine_ft(lat, lon, row["lat"], row["lon"]) > radius_ft:
                    continue
                parcels.append(
                    Parcel(
                        parcel_id=row["parcel_id"],
                        address=row["address"],
                        city=row["city"],
                        state="AZ",
                        zip_code=row["zip_code"],
                        lat=row["lat"],
                        lon=row["lon"],
                        year_built=row["year_built"],
                        lot_size_sqft=row["lot_size_sqft"],
                        estimated_value=float(row["value"]) if row["value"] is not None else None,
                        owner_name=row["owner_name"],
                        assessor_url=SOURCE_PAGE,
                        provenance=Provenance(source=SOURCE, source_url=SOURCE_PAGE, retrieved_at=now),
                    )
                )
            return parcels

        return _cached(f"maricopa:parcels:{lat:.6f}:{lon:.6f}:{radius_ft:.0f}", produce)
