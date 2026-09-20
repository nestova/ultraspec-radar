"""Providers backed by the Regrid parcel API (`REGRID_API_TOKEN`).

Regrid serves standardized assessor parcels nationwide — owner names, year
built, values, lot size — which unlocks the markets whose public county feeds
lack ownership/age attributes (Bel Air, Seattle Eastside, Atherton).

The sandbox plan is metered (~2000 parcels/month), so every request here is
shaped to stay frugal: server-side filters (year built, minimum lot size),
`limit=1000` pages with a hard page cap, payload trimming (no geometry,
buildings, zoning or enhanced ownership), and a 10-minute in-process cache
identical to the other providers.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.geo import haversine_ft
from app.models import AnchorHome, Parcel, Provenance
from app.providers.attom import MissingCredentialsError
from app.providers.miamidade import ProviderUnavailableError

API_URL = "https://app.regrid.com/api/v2/parcels/query"
CACHE_TTL_SECONDS = 600
PAGE_SIZE = 1000
MAX_PAGES = 4  # hard cap: 4000 parcels per query, quota guard
MIN_LOT_SQFT = 5000  # server-side floor drops condos/ROW from every pull
QUOTA_WARN_PARCELS = 1500  # sandbox plan is ~2000 parcels/month

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegridMarket:
    """Scan area for one market: a center point and radius in meters."""

    market: str
    state: str
    lat: float
    lon: float
    radius_m: int


REGRID_MARKETS: dict[str, RegridMarket] = {
    "bel-air-beverly-hills-ca": RegridMarket(
        "bel-air-beverly-hills-ca", "CA", 34.0815, -118.4215, 4500
    ),
    "seattle-eastside-wa": RegridMarket(
        "seattle-eastside-wa", "WA", 47.6240, -122.2255, 2000
    ),
    "atherton-ca": RegridMarket("atherton-ca", "CA", 37.4550, -122.1980, 3000),
}

# Trim every payload flag Regrid offers — the app only reads attributes.
_PAYLOAD_TRIM = {
    "return_geometry": "false",
    "return_matched_buildings": "false",
    "return_matched_addresses": "false",
    "return_enhanced_ownership": "false",
    "return_zoning": "false",
    "return_stacked": "false",
}

_cache: dict[str, tuple[float, list]] = {}
_fetched_parcels = 0
_quota_warned = False


def _cached(key: str, produce):
    hit = _cache.get(key)
    if hit is not None and hit[0] > time.monotonic():
        return hit[1]
    value = produce()
    _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, value)
    return value


def clear_cache() -> None:
    _cache.clear()


def _account_usage(count: int) -> None:
    """Track parcels pulled this process against the metered sandbox plan."""
    global _fetched_parcels, _quota_warned
    _fetched_parcels += count
    if not _quota_warned and _fetched_parcels >= QUOTA_WARN_PARCELS:
        _quota_warned = True
        logger.warning(
            "Regrid sandbox quota: ~%d parcels fetched this process (plan allows "
            "~2000/month). Scans repeat free within 10 minutes via cache.",
            _fetched_parcels,
        )


def _features(payload: dict) -> list[dict]:
    """Accept either a root FeatureCollection or Regrid's wrapped response."""
    collection = payload.get("parcels", payload)
    return collection.get("features", [])


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _to_int(value) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _query(token: str, params: dict, transport: httpx.BaseTransport | None) -> list[dict]:
    """GET one Regrid query, paging forward with `offset_id` (max 4 pages)."""
    request_params = {**params, "token": token, "limit": PAGE_SIZE, **_PAYLOAD_TRIM}
    features: list[dict] = []
    with httpx.Client(timeout=60.0, transport=transport) as client:
        offset = 0
        for _ in range(MAX_PAGES):
            try:
                response = client.get(API_URL, params={**request_params, "offset_id": offset})
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError(f"Regrid request failed: {exc}") from exc
            if response.status_code in (401, 403):
                raise MissingCredentialsError(
                    f"Regrid rejected the API token (HTTP {response.status_code}). "
                    "Check REGRID_API_TOKEN in the Secrets settings."
                )
            if response.status_code != 200:
                raise ProviderUnavailableError(
                    f"Regrid API returned HTTP {response.status_code}: {response.text[:300]}"
                )
            page = _features(response.json())
            features.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset = page[-1].get("id")
            if offset is None:
                break
    _account_usage(len(features))
    return features


def _row(feature: dict) -> dict | None:
    """Map a Regrid feature's properties onto the app's parcel row shape.

    API v2 nests the standard-schema attributes under `properties.fields`.
    """
    props = feature.get("properties") or {}
    p = props.get("fields") or props
    lat, lon = _to_float(p.get("lat")), _to_float(p.get("lon"))
    if lat is None or lon is None:
        return None
    return {
        "parcel_id": p.get("parcelnumb") or props.get("ll_uuid") or feature.get("id"),
        "address": p.get("address") or "",
        "city": p.get("scity") or "",
        "zip_code": p.get("szip") or "",
        "lat": lat,
        "lon": lon,
        "year_built": _to_int(p.get("yearbuilt")),
        "lot_size_sqft": _to_int(p.get("ll_gissqft")),
        "value": _to_float(p.get("parval")),
        "owner_name": p.get("owner") or "",
    }


class _RegridBase:
    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self._token_value = token
        self._transport = transport

    @property
    def name(self) -> str:  # pragma: no cover - trivial
        raise NotImplementedError

    def _token(self) -> str:
        token = self._token_value or os.getenv("REGRID_API_TOKEN")
        if not token:
            raise MissingCredentialsError(
                "REGRID_API_TOKEN is not set. Add the Regrid sandbox token in the "
                "Secrets settings to scan Regrid-backed markets."
            )
        return token

    def _market(self, market: str) -> RegridMarket:
        config = REGRID_MARKETS.get(market)
        if config is None:
            raise ValueError(
                f"Regrid providers only support {sorted(REGRID_MARKETS)}, got '{market}'."
            )
        return config


class RegridListingProvider(_RegridBase):
    """Anchor homes from a Regrid scan area."""

    name = "regrid:anchors"

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        config = self._market(market)
        now = datetime.now(timezone.utc)

        def produce() -> list[AnchorHome]:
            features = _query(
                self._token(),
                {
                    "lat": config.lat,
                    "lon": config.lon,
                    "radius": config.radius_m,
                    "fields[yearbuilt][gte]": int(min_year_built),
                    "fields[ll_gissqft][gte]": MIN_LOT_SQFT,
                },
                self._transport,
            )
            anchors = [
                AnchorHome(
                    id=row["parcel_id"],
                    address=row["address"],
                    city=row["city"],
                    state=config.state,
                    zip_code=row["zip_code"],
                    lat=row["lat"],
                    lon=row["lon"],
                    price=row["value"],
                    status="sold",
                    year_built=row["year_built"],
                    parcel_id=row["parcel_id"],
                    provenance=Provenance(
                        source="regrid", source_url="https://regrid.com/", retrieved_at=now
                    ),
                )
                for f in features
                if (row := _row(f)) is not None
                and row["value"] is not None
                and row["value"] >= min_price
            ]
            anchors.sort(key=lambda a: -a.price)
            return anchors

        return _cached(f"{market}:anchors:{min_price:.0f}:{int(min_year_built)}", produce)


class RegridParcelProvider(_RegridBase):
    """Neighboring parcels within a radius of an anchor."""

    name = "regrid:parcels"

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        config = self._market(market)
        now = datetime.now(timezone.utc)

        def produce() -> list[Parcel]:
            features = _query(
                self._token(),
                {
                    "lat": lat,
                    "lon": lon,
                    "radius": min(int(radius_ft * 0.3048), 32000),
                    "fields[ll_gissqft][gte]": MIN_LOT_SQFT,
                },
                self._transport,
            )
            rows = [
                row
                for f in features
                if (row := _row(f)) is not None
                and haversine_ft(lat, lon, row["lat"], row["lon"]) <= radius_ft
            ]
            return [
                Parcel(
                    parcel_id=row["parcel_id"],
                    address=row["address"],
                    city=row["city"],
                    state=config.state,
                    zip_code=row["zip_code"],
                    lat=row["lat"],
                    lon=row["lon"],
                    year_built=row["year_built"],
                    lot_size_sqft=row["lot_size_sqft"],
                    estimated_value=row["value"],
                    owner_name=row["owner_name"],
                    assessor_url="https://regrid.com/",
                    provenance=Provenance(
                        source="regrid", source_url="https://regrid.com/", retrieved_at=now
                    ),
                )
                for row in rows
            ]

        return _cached(f"{market}:parcels:{lat:.6f}:{lon:.6f}:{radius_ft:.0f}", produce)
