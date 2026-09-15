import json
from functools import lru_cache
from pathlib import Path

from app.geo import haversine_ft
from app.models import AnchorHome, Parcel

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=8)
def _load_market(market: str) -> dict:
    path = DATA_DIR / f"{market}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in DATA_DIR.glob("*.json")))
        raise FileNotFoundError(f"No fixture dataset for market '{market}'. Available: {available}")
    return json.loads(path.read_text())


def available_markets() -> list[dict]:
    markets = []
    for path in sorted(DATA_DIR.glob("*.json")):
        payload = json.loads(path.read_text())
        markets.append({"id": path.stem, "label": payload.get("label", path.stem)})
    return markets


class FixtureListingProvider:
    """Offline dataset of $15M+ new-construction records for a pilot market.

    Stands in for a licensed feed (Bridge/MLS, ATTOM, CoreLogic) so the pipeline
    can run without scraping Zillow, which its terms of service prohibit.
    """

    name = "fixture:listings"

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        payload = _load_market(market)
        anchors = [AnchorHome(**record) for record in payload["anchors"]]
        return [a for a in anchors if a.price >= min_price and a.year_built >= min_year_built]


class FixtureParcelProvider:
    """Offline county GIS / assessor parcel layer for a pilot market."""

    name = "fixture:parcels"

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        payload = _load_market(market)
        parcels = [Parcel(**record) for record in payload["parcels"]]
        return [p for p in parcels if haversine_ft(lat, lon, p.lat, p.lon) <= radius_ft]
