"""Miami-Dade County Property Appraiser data provider.

Queries the county's public ArcGIS REST Feature Service (Property Point View)
for real property data — no API key needed.  Implements both ``ListingProvider``
(anchors) and ``ParcelProvider`` (nearby candidate parcels).

Data source:
  https://gis-mdc.opendata.arcgis.com/datasets/MDC::property-point-view/about
  Feature Service:
  https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/PaGISView_gdb/FeatureServer/0
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import httpx

from app.geo import haversine_ft
from app.models import AnchorHome, Parcel, Provenance

logger = logging.getLogger(__name__)

FEATURE_SERVER = (
    "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny"
    "/arcgis/rest/services/PaGISView_gdb/FeatureServer/0/query"
)

# Single-family residential DOR codes start with "01".
_SF_DOR_FILTER = "DOR_CODE_CUR LIKE '01%'"

# Fields we always request.
_OUT_FIELDS = ",".join([
    "FOLIO", "TRUE_SITE_ADDR", "TRUE_SITE_CITY", "TRUE_SITE_ZIP_CODE",
    "TRUE_OWNER1", "YEAR_BUILT", "ASSESSED_VAL_CUR", "LOT_SIZE",
    "BEDROOM_COUNT", "BATHROOM_COUNT", "BUILDING_HEATED_AREA",
    "PRICE_1", "DATEOFSALE_UTC", "DOR_DESC",
])

_MAX_RECORDS = 1000


def _query(where: str, geometry: str | None = None, result_count: int = 200) -> list[dict]:
    """Execute an ArcGIS REST query and return a list of feature attribute dicts."""
    params: dict[str, str | int] = {
        "f": "json",
        "where": where,
        "outFields": _OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": result_count,
    }
    if geometry:
        params["geometry"] = geometry
        params["geometryType"] = "esriGeometryEnvelope"
        params["inSR"] = "4326"
        params["spatialRel"] = "esriSpatialRelIntersects"

    with httpx.Client(timeout=30.0) as client:
        r = client.post(FEATURE_SERVER, data=params)
        r.raise_for_status()
        data = r.json()

    if "error" in data:
        raise RuntimeError(f"ArcGIS query error: {data['error'].get('message', data['error'])}")

    features = data.get("features", [])
    return [f.get("attributes", {}) | {"_lat": f.get("geometry", {}).get("y"), "_lon": f.get("geometry", {}).get("x")} for f in features]


def _bbox(lat: float, lon: float, radius_ft: float) -> str:
    """Build a WGS84 bounding-box envelope string around a point."""
    lat_delta = radius_ft / 364_000.0
    lon_delta = radius_ft / (364_000.0 * max(math.cos(math.radians(lat)), 0.01))
    return f"{lon - lon_delta},{lat - lat_delta},{lon + lon_delta},{lat + lat_delta}"


def _zip_clean(zip_code: str | None) -> str:
    if not zip_code:
        return ""
    return zip_code.split("-")[0]


class MiamiDadeListingProvider:
    """Fetches high-value new-construction single-family homes from Miami-Dade assessor data."""

    name = "miami-dade"

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        where = f"{_SF_DOR_FILTER} AND YEAR_BUILT >= {int(min_year_built)} AND ASSESSED_VAL_CUR >= {int(min_price)}"
        rows = _query(where, result_count=200)
        logger.info("Miami-Dade anchors: %d results (min_price=%s, min_year=%s)", len(rows), min_price, min_year_built)

        anchors: list[AnchorHome] = []
        for row in rows:
            lat, lon = row.get("_lat"), row.get("_lon")
            if lat is None or lon is None:
                continue
            folio = row.get("FOLIO")
            anchors.append(AnchorHome(
                id=folio or f"md-{row.get('TRUE_SITE_ADDR', '')}",
                address=row.get("TRUE_SITE_ADDR", ""),
                city=row.get("TRUE_SITE_CITY", ""),
                state="FL",
                zip_code=_zip_clean(row.get("TRUE_SITE_ZIP_CODE")),
                lat=float(lat),
                lon=float(lon),
                price=float(row.get("ASSESSED_VAL_CUR") or 0.0),
                status="sold",
                year_built=row.get("YEAR_BUILT") or 0,
                parcel_id=folio,
                provenance=Provenance(
                    source="miami-dade-pa",
                    source_url=f"https://www.miamidadepa.gov/property-search?folio={folio}" if folio else None,
                    retrieved_at=datetime.now(timezone.utc),
                ),
            ))
        return anchors


class MiamiDadeParcelProvider:
    """Fetches nearby single-family parcels from Miami-Dade assessor data."""

    name = "miami-dade"

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        envelope = _bbox(lat, lon, radius_ft)
        rows = _query(_SF_DOR_FILTER, geometry=envelope, result_count=_MAX_RECORDS)
        logger.info("Miami-Dade parcels near (%s, %s) r=%s ft: %d raw results", lat, lon, radius_ft, len(rows))

        parcels: list[Parcel] = []
        for row in rows:
            p_lat, p_lon = row.get("_lat"), row.get("_lon")
            if p_lat is None or p_lon is None:
                continue
            if haversine_ft(lat, lon, float(p_lat), float(p_lon)) > radius_ft:
                continue
            folio = row.get("FOLIO")
            parcels.append(Parcel(
                parcel_id=folio or f"md-{row.get('TRUE_SITE_ADDR', '')}",
                address=row.get("TRUE_SITE_ADDR", ""),
                city=row.get("TRUE_SITE_CITY", ""),
                state="FL",
                zip_code=_zip_clean(row.get("TRUE_SITE_ZIP_CODE")),
                lat=float(p_lat),
                lon=float(p_lon),
                year_built=row.get("YEAR_BUILT"),
                lot_size_sqft=float(row.get("LOT_SIZE")) if row.get("LOT_SIZE") else None,
                estimated_value=float(row.get("ASSESSED_VAL_CUR")) if row.get("ASSESSED_VAL_CUR") else None,
                owner_name=row.get("TRUE_OWNER1"),
                provenance=Provenance(
                    source="miami-dade-pa",
                    source_url=f"https://www.miamidadepa.gov/property-search?folio={folio}" if folio else None,
                    retrieved_at=datetime.now(timezone.utc),
                ),
            ))
        return parcels
