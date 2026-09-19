"""Providers backed by generic public county ArcGIS parcel layers.

One class pair serves every market configured in `county_sources.py`:

* Bulk markets (Collier, Manatee, NYS/Hamptons) fetch the whole market
  slice once, cache it briefly, and filter anchors/radii in memory —
  the same pattern as the Maricopa provider.
* Query markets (Mecklenburg, Clark) push the anchor filter to the
  server and run small envelope queries per anchor radius, caching each
  response briefly.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.geo import haversine_ft
from app.models import AnchorHome, Parcel, Provenance
from app.providers.arcgis_rest import envelope_4326, query_arcgis
from app.providers.county_sources import CountySource

CACHE_TTL_SECONDS = 600
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, produce):
    hit = _cache.get(key)
    if hit is not None and hit[0] > time.monotonic():
        return hit[1]
    value = produce()
    _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, value)
    return value


def clear_cache() -> None:
    _cache.clear()


def _require_market(source: CountySource, market: str) -> None:
    if market != source.market:
        raise ValueError(
            f"'{source.source}' providers only support market '{source.market}', got '{market}'."
        )


def _bulk_rows(source: CountySource, transport: httpx.BaseTransport | None) -> list[dict]:
    """The cached whole-market roll (bulk markets only)."""

    def produce() -> list[dict]:
        features = query_arcgis(
            source.query_url,
            {
                "where": source.bulk_where,
                "outFields": ",".join(source.out_fields),
                "returnCentroid": "true",
                "outSR": "4326",
            },
            transport=transport,
            page_size=source.page_size,
        )
        rows = [row for f in features if (row := source.row_builder(f)) is not None]
        if source.enrich_years:
            source.enrich_years(rows, transport)
        return rows

    return _cached(f"{source.market}:rows", produce)


def _query_rows(
    source: CountySource,
    params: dict[str, Any],
    transport: httpx.BaseTransport | None,
) -> list[dict]:
    features = query_arcgis(source.query_url, params, transport=transport, page_size=source.page_size)
    rows: list[dict] = []
    seen: set[str] = set()
    for f in features:
        row = source.row_builder(f)
        if row is None or row["parcel_id"] in seen:
            continue
        seen.add(row["parcel_id"])
        rows.append(row)
    if source.enrich_years:
        source.enrich_years(rows, transport)
    return rows


def _anchor_params(source: CountySource, min_price: float, min_year_built: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "where": source.anchor_where.format(min_price=int(min_price), min_year=int(min_year_built)),
        "outFields": ",".join(source.out_fields),
        "returnCentroid": "true",
        "outSR": "4326",
    }
    if source.anchor_envelope:
        params["geometry"] = json.dumps(source.anchor_envelope)
        params["geometryType"] = "esriGeometryEnvelope"
        params["inSR"] = "4326"
        params["spatialRel"] = "esriSpatialRelIntersects"
    return params


class CountyListingProvider:
    """Anchor homes from a county assessor roll."""

    def __init__(self, source: CountySource, transport: httpx.BaseTransport | None = None) -> None:
        self.name = f"county:{source.market}:anchors"
        self._source = source
        self._transport = transport

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        source = self._source
        _require_market(source, market)
        now = datetime.now(timezone.utc)

        def produce() -> list[AnchorHome]:
            rows = (
                _bulk_rows(source, self._transport)
                if source.bulk_where
                else _query_rows(source, _anchor_params(source, min_price, min_year_built), self._transport)
            )
            anchors = [
                AnchorHome(
                    id=row["parcel_id"],
                    address=row["address"],
                    city=row["city"],
                    state=source.state,
                    zip_code=row["zip_code"],
                    lat=row["lat"],
                    lon=row["lon"],
                    price=float(row["value"]),
                    status="sold",
                    year_built=row["year_built"],
                    parcel_id=row["parcel_id"],
                    provenance=Provenance(
                        source=source.source, source_url=source.source_page, retrieved_at=now
                    ),
                )
                for row in rows
                if row["value"] is not None
                and row["value"] >= min_price
                and row["year_built"] is not None
                and row["year_built"] >= min_year_built
            ]
            anchors.sort(key=lambda a: -a.price)
            return anchors

        return _cached(f"{source.market}:anchors:{min_price:.0f}:{int(min_year_built)}", produce)


class CountyParcelProvider:
    """Neighboring parcels from a county assessor roll."""

    def __init__(self, source: CountySource, transport: httpx.BaseTransport | None = None) -> None:
        self.name = f"county:{source.market}:parcels"
        self._source = source
        self._transport = transport

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        source = self._source
        _require_market(source, market)
        now = datetime.now(timezone.utc)

        def produce() -> list[Parcel]:
            if source.bulk_where:
                rows = [
                    row
                    for row in _bulk_rows(source, self._transport)
                    if haversine_ft(lat, lon, row["lat"], row["lon"]) <= radius_ft
                ]
            else:
                rows = _query_rows(
                    source,
                    {
                        "where": source.parcels_where,
                        "outFields": ",".join(source.out_fields),
                        "geometry": json.dumps(envelope_4326(lat, lon, radius_ft)),
                        "geometryType": "esriGeometryEnvelope",
                        "inSR": "4326",
                        "spatialRel": "esriSpatialRelIntersects",
                        "returnCentroid": "true",
                        "outSR": "4326",
                    },
                    self._transport,
                )
                rows = [
                    row
                    for row in rows
                    if haversine_ft(lat, lon, row["lat"], row["lon"]) <= radius_ft
                ]
            return [
                Parcel(
                    parcel_id=row["parcel_id"],
                    address=row["address"],
                    city=row["city"],
                    state=source.state,
                    zip_code=row["zip_code"],
                    lat=row["lat"],
                    lon=row["lon"],
                    year_built=row["year_built"],
                    lot_size_sqft=row["lot_size_sqft"],
                    estimated_value=float(row["value"]) if row["value"] is not None else None,
                    owner_name=row["owner_name"],
                    assessor_url=source.source_page,
                    provenance=Provenance(
                        source=source.source, source_url=source.source_page, retrieved_at=now
                    ),
                )
                for row in rows
            ]

        return _cached(f"{source.market}:parcels:{lat:.6f}:{lon:.6f}:{radius_ft:.0f}", produce)
