from datetime import datetime, timezone

from app.clustering import cluster_anchors
from app.config import SearchConfig
from app.export import candidates_to_csv
from app.geo import haversine_ft
from app.models import AnchorHome, Parcel, Provenance
from app.pipeline import run_pipeline
from app.providers import FixtureListingProvider, FixtureParcelProvider

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


def _provenance() -> Provenance:
    return Provenance(source="test", source_url=None, retrieved_at=NOW)


def _anchor(anchor_id: str, lat: float, lon: float, price: float = 20_000_000) -> AnchorHome:
    return AnchorHome(
        id=anchor_id,
        address=f"{anchor_id} Test St",
        city="Miami Beach",
        state="FL",
        zip_code="33139",
        lat=lat,
        lon=lon,
        price=price,
        status="sold",
        year_built=2024,
        provenance=_provenance(),
    )


def _parcel(parcel_id: str, lat: float, lon: float, owner: str, value: float, year: int) -> Parcel:
    return Parcel(
        parcel_id=parcel_id,
        address=f"{parcel_id} Test St",
        city="Miami Beach",
        state="FL",
        zip_code="33139",
        lat=lat,
        lon=lon,
        year_built=year,
        lot_size_sqft=10_000,
        estimated_value=value,
        owner_name=owner,
        provenance=_provenance(),
    )


class StubListings:
    name = "stub"

    def __init__(self, anchors: list[AnchorHome]) -> None:
        self.anchors = anchors

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        return [a for a in self.anchors if a.price >= min_price and a.year_built >= min_year_built]


class StubParcels:
    name = "stub"

    def __init__(self, parcels: list[Parcel]) -> None:
        self.parcels = parcels

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        return [p for p in self.parcels if haversine_ft(lat, lon, p.lat, p.lon) <= radius_ft]


def test_singletons_discarded_unless_overridden() -> None:
    anchors = [_anchor("a1", 25.79, -80.14), _anchor("a2", 25.7905, -80.14), _anchor("far", 25.9, -80.3)]
    clusters = cluster_anchors(anchors, radius_miles=0.5, min_members=2, allow_singletons=False)
    assert [len(c) for c in clusters] == [2]

    with_singletons = cluster_anchors(anchors, radius_miles=0.5, min_members=2, allow_singletons=True)
    assert sorted(len(c) for c in with_singletons) == [1, 2]


def test_filters_and_ranking() -> None:
    anchors = [_anchor("a1", 25.7900, -80.1400), _anchor("a2", 25.7905, -80.1400)]
    parcels = [
        _parcel("keep-close", 25.79005, -80.14005, "Robert Alvarez", 1_200_000, 1955),
        _parcel("keep-trust", 25.79020, -80.14010, "Smith Family Trust", 2_400_000, 1968),
        _parcel("drop-llc", 25.79010, -80.14002, "Bay Road Holdings LLC", 1_100_000, 1950),
        _parcel("drop-expensive", 25.79012, -80.14004, "Linda Brennan", 3_900_000, 1950),
        _parcel("drop-new", 25.79014, -80.14006, "Linda Brennan", 1_100_000, 1999),
        _parcel("drop-far", 25.7990, -80.1500, "Linda Brennan", 1_100_000, 1950),
    ]
    result = run_pipeline(SearchConfig(), StubListings(anchors), StubParcels(parcels))

    assert len(result.clusters) == 1
    ids = [c.parcel.parcel_id for c in result.clusters[0].candidates]
    assert ids == ["keep-close", "keep-trust"]
    assert result.clusters[0].candidates[0].distance_to_anchor_ft < 100
    assert result.summary.candidates_returned == 2


def test_candidate_cap_is_configurable() -> None:
    anchors = [_anchor("a1", 25.7900, -80.1400), _anchor("a2", 25.7905, -80.1400)]
    parcels = [
        _parcel(f"p{i}", 25.7900 + i * 0.00002, -80.1400, "Robert Alvarez", 1_000_000 + i, 1950)
        for i in range(15)
    ]
    config = SearchConfig(max_candidates_per_cluster=3)
    result = run_pipeline(config, StubListings(anchors), StubParcels(parcels))
    assert len(result.clusters[0].candidates) == 3


def test_fixture_market_runs_end_to_end() -> None:
    result = run_pipeline(SearchConfig(), FixtureListingProvider(), FixtureParcelProvider())
    assert result.summary.anchors_found > 0
    assert result.summary.clusters_found > 0
    assert result.summary.candidates_returned > 0
    for cluster in result.clusters:
        assert len(cluster.candidates) <= 10
        for candidate in cluster.candidates:
            assert candidate.parcel.estimated_value <= 2_500_000
            assert candidate.parcel.year_built <= 1970
            assert candidate.ownership.ownership_type in {"individual", "trust"}
            assert candidate.distance_to_anchor_ft <= 500

    csv_text = candidates_to_csv(result)
    assert "owner_name" in csv_text.splitlines()[0]
    assert len(csv_text.splitlines()) == result.summary.candidates_returned + 1
