import json

from app.config import SearchConfig
from app.pipeline import run_pipeline
from app.providers import FixtureListingProvider, FixtureParcelProvider
from app.waterfront import DATA_PATH, WaterIndex, is_waterfront


def test_point_in_water_and_near_shore() -> None:
    index = WaterIndex.from_geojson(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[-80.20, 25.70], [-80.10, 25.70], [-80.10, 25.80], [-80.20, 25.80], [-80.20, 25.70]]
                        ],
                    },
                }
            ],
        }
    )
    # inside the water polygon
    assert index.is_waterfront(25.75, -80.15)
    # ~180 ft north of the shoreline at this latitude
    assert index.is_waterfront(25.8005, -80.15)
    # ~550 ft north of the shoreline
    assert not index.is_waterfront(25.8015, -80.15)
    # far inland
    assert not index.is_waterfront(25.95, -80.15)


def test_land_holes_are_not_water() -> None:
    index = WaterIndex.from_geojson(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[-80.30, 25.70], [-80.10, 25.70], [-80.10, 25.90], [-80.30, 25.90], [-80.30, 25.70]],
                            [[-80.26, 25.74], [-80.22, 25.74], [-80.22, 25.78], [-80.26, 25.78], [-80.26, 25.74]],
                        ],
                    },
                }
            ],
        }
    )
    # in the bay, outside the island hole
    assert index.is_waterfront(25.72, -80.15)
    # on the island (a hole = land)
    assert not index.is_waterfront(25.76, -80.24)


def test_real_dataset_classification() -> None:
    if not DATA_PATH.exists():
        return
    assert is_waterfront(25.79, -80.17) is True  # Biscayne Bay
    assert is_waterfront(25.76, -80.30) is False  # inland Miami
    assert is_waterfront(40.85, -72.45) is True  # Shinnecock Bay, Hamptons


def test_pipeline_waterfront_filter_and_annotation() -> None:
    config = SearchConfig(market="miami-dade-fl")
    result = run_pipeline(config, FixtureListingProvider(), FixtureParcelProvider())
    all_candidates = [c for cluster in result.clusters for c in cluster.candidates]

    watermarked = [c for c in all_candidates if c.parcel.waterfront is not None]
    assert watermarked, "expected the real water dataset to annotate fixture parcels"

    filtered = run_pipeline(
        config.model_copy(update={"waterfront_only": True}),
        FixtureListingProvider(),
        FixtureParcelProvider(),
    )
    kept = [c for cluster in filtered.clusters for c in cluster.candidates]
    assert all(c.parcel.waterfront for c in kept)
    kept_ids = {c.parcel.parcel_id for c in kept}
    assert kept_ids <= {c.parcel.parcel_id for c in all_candidates}


def test_fixture_dataset_is_valid_geojson() -> None:
    if not DATA_PATH.exists():
        return
    payload = json.loads(DATA_PATH.read_text())
    assert payload["type"] == "FeatureCollection"
    assert payload["features"]
