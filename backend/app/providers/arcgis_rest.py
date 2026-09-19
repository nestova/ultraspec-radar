"""Shared helpers for querying public county ArcGIS REST endpoints.

Every county feed in this app speaks the ArcGIS query protocol; only the
URL, WHERE clause and field names differ. These helpers centralize request
execution, pagination, error mapping and small conversions so county
providers stay declarative.
"""

from __future__ import annotations

import math
from typing import Any

import httpx

from app.providers.miamidade import ProviderUnavailableError

FEET_PER_DEGREE_LAT = 364_000.0


def query_arcgis(
    query_url: str,
    params: dict[str, Any],
    transport: httpx.BaseTransport | None = None,
    page_size: int | None = None,
) -> list[dict]:
    """POST one ArcGIS query and return raw feature dicts.

    When `page_size` is given, the query pages forward with `resultOffset`
    until a short page arrives (the bulk-fetch pattern). Raises
    ProviderUnavailableError on network, HTTP or query errors so the API
    maps the failure to a 502.
    """
    features: list[dict] = []
    offset = 0
    with httpx.Client(timeout=60.0, transport=transport) as client:
        while True:
            request: dict[str, Any] = dict(params)
            request["f"] = "json"
            request.setdefault("returnGeometry", "false")
            if page_size:
                request["resultRecordCount"] = page_size
                request["resultOffset"] = offset
            try:
                response = client.post(query_url, data=request)
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError(f"County GIS request failed: {exc}") from exc
            if response.status_code != 200:
                raise ProviderUnavailableError(
                    f"County GIS endpoint returned HTTP {response.status_code}."
                )
            payload = response.json()
            if "error" in payload:
                raise ProviderUnavailableError(
                    f"County GIS query error: {payload['error'].get('message', payload['error'])}"
                )
            page = payload.get("features", [])
            features.extend(page)
            if not page_size or len(page) < page_size:
                return features
            offset += page_size


def envelope_4326(lat: float, lon: float, radius_ft: float) -> dict[str, Any]:
    """A WGS84 envelope (ArcGIS geometry JSON) around a point, in feet."""
    d_lat = radius_ft / FEET_PER_DEGREE_LAT
    d_lon = d_lat / max(math.cos(math.radians(lat)), 0.01)
    return {
        "xmin": lon - d_lon,
        "ymin": lat - d_lat,
        "xmax": lon + d_lon,
        "ymax": lat + d_lat,
        "spatialReference": {"wkid": 4326},
    }


def to_float(value: Any) -> float | None:
    """Tolerant float coercion — county layers ship comma strings and blanks."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return int(number) if number is not None else None
