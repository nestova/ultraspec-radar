"""Providers backed by Miami-Dade County's public Property Appraiser + GIS data.

Both providers query the county's open "Property Point View" layer — the
Property Appraiser's certified tax roll published on the Miami-Dade GIS open
data hub (ArcGIS Hub). Public data, no credentials, no scraping:

    https://gis-mdc.opendata.arcgis.com/datasets/MDC::property-point-view/about

The layer exposes folio, site address, owner names, year built, current
assessed value, lot size and DOR use code, with point geometry. Anchors are
found by value + year built + single-family use code (DOR 0101); nearby
parcels come from a server-side radius query around each anchor.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from app.models import AnchorHome, Parcel, Provenance

MARKET = "miami-dade-fl"
SINGLE_FAMILY_DOR = "0101"
QUERY_URL = (
    "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/"
    "PaGISView_gdb/FeatureServer/0/query"
)
SOURCE = "Miami-Dade Property Appraiser - Property Point View (county GIS hub)"
SOURCE_PAGE = "https://gis-mdc.opendata.arcgis.com/datasets/MDC::property-point-view/about"
PROPERTY_SEARCH_URL = "https://apps.miamidadepa.gov/PropertySearch/"
PAGE_SIZE = 2000  # the layer's maxRecordCount
CACHE_TTL_SECONDS = 600

ANCHOR_FIELDS = ",".join(
    ["FOLIO", "TRUE_SITE_ADDR", "TRUE_SITE_CITY", "TRUE_SITE_ZIP_CODE", "YEAR_BUILT", "ASSESSED_VAL_CUR"]
)
PARCEL_FIELDS = ",".join(
    [
        "FOLIO",
        "TRUE_SITE_ADDR",
        "TRUE_SITE_CITY",
        "TRUE_SITE_ZIP_CODE",
        "TRUE_OWNER1",
        "TRUE_OWNER2",
        "TRUE_OWNER3",
        "YEAR_BUILT",
        "ASSESSED_VAL_CUR",
        "LOT_SIZE",
    ]
)


class ProviderUnavailableError(RuntimeError):
    """The county GIS endpoint could not be reached or returned an error."""


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
        raise ValueError(f"Miami-Dade providers only support market '{MARKET}', got '{market}'.")


def _query(params: dict[str, Any], transport: httpx.BaseTransport | None) -> list[dict]:
    """Run an ArcGIS query, paginating past the layer's maxRecordCount."""
    features: list[dict] = []
    offset = 0
    with httpx.Client(timeout=30.0, transport=transport) as client:
        while True:
            request = {**params, "f": "json", "resultOffset": offset, "resultRecordCount": PAGE_SIZE}
            try:
                response = client.post(QUERY_URL, data=request)
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError(f"Miami-Dade GIS request failed: {exc}") from exc
            if response.status_code != 200:
                raise ProviderUnavailableError(f"Miami-Dade GIS returned HTTP {response.status_code}.")
            payload = response.json()
            if "error" in payload:
                raise ProviderUnavailableError(
                    f"Miami-Dade GIS query error: {payload['error'].get('message', payload['error'])}"
                )
            features.extend(payload.get("features", []))
            if not payload.get("exceededTransferLimit"):
                return features
            offset += PAGE_SIZE


def _owner_name(attrs: dict[str, Any]) -> str | None:
    owners = (attrs.get("TRUE_OWNER1"), attrs.get("TRUE_OWNER2"), attrs.get("TRUE_OWNER3"))
    return " ".join(str(n).strip() for n in owners if n) or None


class MiamiDadeListingProvider:
    """Anchor homes from the Property Appraiser's certified roll.

    An anchor is a single-family parcel (DOR 0101) whose current assessed
    value is at least `min_price` and whose year built is at least
    `min_year_built` — the appraiser's counterpart of "$15M+ new construction".
    """

    name = "miamidade:anchors"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        _require_market(market)
        where = (
            f"DOR_CODE_CUR = '{SINGLE_FAMILY_DOR}' AND "
            f"YEAR_BUILT >= {int(min_year_built)} AND ASSESSED_VAL_CUR >= {min_price:.0f}"
        )

        def produce() -> list[AnchorHome]:
            features = _query(
                {
                    "where": where,
                    "outFields": ANCHOR_FIELDS,
                    "orderByFields": "ASSESSED_VAL_CUR DESC",
                    "outSR": 4326,
                    "returnGeometry": "true",
                },
                self._transport,
            )
            now = datetime.now(timezone.utc)
            anchors = []
            for feature in features:
                attrs = feature["attributes"]
                geom = feature.get("geometry") or {}
                if "y" not in geom or "x" not in geom or attrs.get("ASSESSED_VAL_CUR") is None:
                    continue
                folio = str(attrs["FOLIO"])
                anchors.append(
                    AnchorHome(
                        id=folio,
                        address=str(attrs.get("TRUE_SITE_ADDR") or ""),
                        city=str(attrs.get("TRUE_SITE_CITY") or ""),
                        state="FL",
                        zip_code=str(attrs.get("TRUE_SITE_ZIP_CODE") or ""),
                        lat=float(geom["y"]),
                        lon=float(geom["x"]),
                        price=float(attrs["ASSESSED_VAL_CUR"]),
                        status="sold",
                        year_built=int(attrs["YEAR_BUILT"]),
                        parcel_id=folio,
                        provenance=Provenance(source=SOURCE, source_url=SOURCE_PAGE, retrieved_at=now),
                    )
                )
            return [a for a in anchors if a.price >= min_price and a.year_built >= min_year_built]

        return _cached(f"anchors:{min_price:.0f}:{int(min_year_built)}", produce)


class MiamiDadeParcelProvider:
    """Neighboring single-family parcels from the county GIS layer.

    Server-side radius query (feet) around an anchor point. The pipeline
    applies value/age/ownership filters downstream.
    """

    name = "miamidade:parcels"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        _require_market(market)

        def produce() -> list[Parcel]:
            features = _query(
                {
                    "where": f"DOR_CODE_CUR = '{SINGLE_FAMILY_DOR}'",
                    "geometry": json.dumps({"x": lon, "y": lat}),
                    "geometryType": "esriGeometryPoint",
                    "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects",
                    "distance": f"{float(radius_ft):.0f}",
                    "units": "esriSRUnit_Foot",
                    "outFields": PARCEL_FIELDS,
                    "outSR": 4326,
                    "returnGeometry": "true",
                },
                self._transport,
            )
            now = datetime.now(timezone.utc)
            parcels = []
            for feature in features:
                attrs = feature["attributes"]
                geom = feature.get("geometry") or {}
                if "y" not in geom or "x" not in geom:
                    continue
                year_built = attrs.get("YEAR_BUILT")
                parcels.append(
                    Parcel(
                        parcel_id=str(attrs["FOLIO"]),
                        address=str(attrs.get("TRUE_SITE_ADDR") or ""),
                        city=str(attrs.get("TRUE_SITE_CITY") or ""),
                        state="FL",
                        zip_code=str(attrs.get("TRUE_SITE_ZIP_CODE") or ""),
                        lat=float(geom["y"]),
                        lon=float(geom["x"]),
                        year_built=int(year_built) if year_built is not None else None,
                        lot_size_sqft=float(attrs["LOT_SIZE"]) if attrs.get("LOT_SIZE") is not None else None,
                        estimated_value=(
                            float(attrs["ASSESSED_VAL_CUR"])
                            if attrs.get("ASSESSED_VAL_CUR") is not None
                            else None
                        ),
                        owner_name=_owner_name(attrs),
                        assessor_url=PROPERTY_SEARCH_URL,
                        provenance=Provenance(source=SOURCE, source_url=SOURCE_PAGE, retrieved_at=now),
                    )
                )
            return parcels

        return _cached(f"parcels:{lat:.6f}:{lon:.6f}:{radius_ft:.0f}", produce)
