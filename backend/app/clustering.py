import math

import numpy as np
from sklearn.cluster import DBSCAN

from app.models import AnchorHome

EARTH_RADIUS_MILES = 3958.8


def cluster_anchors(
    anchors: list[AnchorHome],
    radius_miles: float,
    min_members: int,
    allow_singletons: bool,
) -> list[list[AnchorHome]]:
    """Group anchors with DBSCAN on haversine distance; optionally keep singletons."""
    if not anchors:
        return []

    coords = np.radians([[a.lat, a.lon] for a in anchors])
    labels = DBSCAN(
        eps=radius_miles / EARTH_RADIUS_MILES,
        min_samples=max(min_members, 1),
        metric="haversine",
    ).fit_predict(coords)

    groups: dict[int, list[AnchorHome]] = {}
    noise: list[AnchorHome] = []
    for anchor, label in zip(anchors, labels, strict=False):
        if label == -1:
            noise.append(anchor)
        else:
            groups.setdefault(int(label), []).append(anchor)

    clusters = [members for members in groups.values() if len(members) >= min_members]
    if allow_singletons:
        clusters.extend([anchor] for anchor in noise)
    return sorted(clusters, key=lambda members: -len(members))


def centroid(anchors: list[AnchorHome]) -> tuple[float, float]:
    x = y = z = 0.0
    for a in anchors:
        lat, lon = math.radians(a.lat), math.radians(a.lon)
        x += math.cos(lat) * math.cos(lon)
        y += math.cos(lat) * math.sin(lon)
        z += math.sin(lat)
    n = len(anchors)
    x, y, z = x / n, y / n, z / n
    lon = math.atan2(y, x)
    lat = math.atan2(z, math.sqrt(x * x + y * y))
    return math.degrees(lat), math.degrees(lon)


def bbox(anchors: list[AnchorHome]) -> tuple[float, float, float, float]:
    lats = [a.lat for a in anchors]
    lons = [a.lon for a in anchors]
    return min(lats), min(lons), max(lats), max(lons)
