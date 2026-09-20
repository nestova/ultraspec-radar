"""Geometric waterfront classification for parcels.

The county tax rolls we scan do not carry a waterfront flag, so parcels are
classified geometrically against ``backend/data/water.geojson`` — water-body
polygons built from Natural Earth 10m ocean + lakes data (see AGENTS.md).
Coverage: oceans, open bays (Biscayne Bay, Shinnecock Bay, …) and major
lakes (Lake Mead, Okeechobee). Enclosed bays (SF Bay, Peconic Bay), Lake
Washington and residential canals are below the dataset's resolution and
will not be flagged.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.models import Parcel

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "water.geojson"

# A parcel counts as waterfront if it sits in water or within this distance of it.
WATERFRONT_MAX_FT = 250.0

FT_PER_DEG_LAT = 110_540 * 3.28084


def _ring_bbox(ring: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _distance_to_ring_ft(lat: float, lon: float, ring: list[list[float]]) -> float:
    """Planar distance from a point to a ring, in feet, in local degrees scale."""
    ft_per_deg_lon = FT_PER_DEG_LAT * math.cos(math.radians(lat))
    px, py = lon * ft_per_deg_lon, lat * FT_PER_DEG_LAT
    best = math.inf
    j = len(ring) - 1
    for i in range(len(ring)):
        x1, y1 = ring[j][0] * ft_per_deg_lon, ring[j][1] * FT_PER_DEG_LAT
        x2, y2 = ring[i][0] * ft_per_deg_lon, ring[i][1] * FT_PER_DEG_LAT
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else ((px - x1) * dx + (py - y1) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        best = min(best, math.hypot(px - (x1 + t * dx), py - (y1 + t * dy)))
        j = i
    return best


class WaterIndex:
    """In-memory index over water polygons: (exterior ring, hole rings) pairs."""

    def __init__(self, polygons: list[tuple[list[list[float]], list[list[list[float]]]]]) -> None:
        self.polygons = polygons
        self.ring_bboxes = [
            [_ring_bbox(exterior)] + [_ring_bbox(h) for h in holes] for exterior, holes in polygons
        ]

    @classmethod
    def from_geojson(cls, payload: dict[str, Any]) -> "WaterIndex":
        polygons: list[tuple[list[list[float]], list[list[list[float]]]]] = []
        for feature in payload.get("features", []):
            geometry = feature.get("geometry") or {}
            parts = (
                [geometry["coordinates"]]
                if geometry.get("type") == "Polygon"
                else geometry.get("coordinates", [])
            )
            for part in parts:
                if part and len(part[0]) >= 3:
                    polygons.append((part[0], part[1:]))
        return cls(polygons)

    @classmethod
    def load(cls, path: Path = DATA_PATH) -> "WaterIndex":
        return cls.from_geojson(json.loads(path.read_text()))

    def is_waterfront(self, lat: float, lon: float, max_ft: float = WATERFRONT_MAX_FT) -> bool:
        for (exterior, holes), _ in zip(self.polygons, self.ring_bboxes, strict=False):
            if _point_in_ring(lon, lat, exterior) and not any(
                _point_in_ring(lon, lat, hole) for hole in holes
            ):
                return True
        margin_lat = max_ft / FT_PER_DEG_LAT
        margin_lon = max_ft / (FT_PER_DEG_LAT * max(math.cos(math.radians(lat)), 1e-9))
        for (exterior, holes), bboxes in zip(self.polygons, self.ring_bboxes, strict=False):
            for ring, (min_lon, min_lat, max_lon, max_lat) in zip(
                [exterior] + holes, bboxes, strict=True
            ):
                if (
                    lon < min_lon - margin_lon
                    or lon > max_lon + margin_lon
                    or lat < min_lat - margin_lat
                    or lat > max_lat + margin_lat
                ):
                    continue
                if _distance_to_ring_ft(lat, lon, ring) <= max_ft:
                    return True
        return False


_index: WaterIndex | None = None
_index_loaded = False


def _get_index() -> WaterIndex | None:
    global _index, _index_loaded
    if not _index_loaded:
        _index_loaded = True
        try:
            _index = WaterIndex.load()
        except FileNotFoundError:
            _index = None
    return _index


def is_waterfront(lat: float, lon: float) -> bool | None:
    """True/False when the water dataset is available, None when it is not."""
    index = _get_index()
    if index is None:
        return None
    return index.is_waterfront(lat, lon)


def annotate_parcels(parcels: list[Parcel]) -> None:
    """Set ``parcel.waterfront`` in place for a batch of parcels."""
    for parcel in parcels:
        parcel.waterfront = is_waterfront(parcel.lat, parcel.lon)
