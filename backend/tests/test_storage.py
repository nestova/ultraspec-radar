from datetime import datetime, timezone

import pytest

from app import storage
from app.models import AnchorHome, Provenance, RunResult, RunSummary


def _run_result(anchors: int = 2, candidates: int = 1) -> RunResult:
    now = datetime.now(timezone.utc)
    provenance = Provenance(source="test", source_url=None, retrieved_at=now)
    anchor = AnchorHome(
        id="a1",
        address="1 Test St",
        city="Miami Beach",
        state="FL",
        zip_code="33139",
        lat=25.8,
        lon=-80.1,
        price=20_000_000,
        status="sold",
        year_built=2024,
        provenance=provenance,
    )
    return RunResult(
        summary=RunSummary(
            market="miami-dade-fl",
            generated_at=now,
            config={"market": "miami-dade-fl"},
            anchors_found=anchors,
            clusters_found=1,
            parcels_scanned=5,
            candidates_returned=candidates,
            stale_sources=[],
            review_queue=[],
        ),
        clusters=[
            {
                "id": "cluster-1",
                "anchor_ids": [anchor.id],
                "anchors": [anchor],
                "centroid_lat": 25.8,
                "centroid_lon": -80.1,
                "bbox": (25.8, -80.1, 25.8, -80.1),
                "avg_anchor_price": 20_000_000,
                "is_singleton": False,
                "candidates": [],
            }
        ],
    )


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_DB_PATH", str(tmp_path / "runs.db"))
    yield


def test_save_list_and_get_round_trip() -> None:
    result = _run_result()
    run_id = storage.save_run(result, "miamidade", "miamidade")
    assert run_id

    runs = storage.list_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == run_id
    assert runs[0]["market"] == "miami-dade-fl"
    assert runs[0]["listing_source"] == "miamidade"
    assert runs[0]["anchors_found"] == 2
    assert runs[0]["candidates_returned"] == 1

    restored = storage.get_run(run_id)
    assert restored.summary.market == "miami-dade-fl"
    assert restored.summary.anchors_found == 2
    assert restored.clusters[0].id == "cluster-1"
    assert restored.clusters[0].anchors[0].id == "a1"


def test_listing_orders_newest_first() -> None:
    storage.save_run(_run_result(), "miamidade", "miamidade")
    storage.save_run(_run_result(anchors=3), "fixture", "fixture")
    runs = storage.list_runs()
    assert len(runs) == 2
    assert runs[0]["anchors_found"] == 3
    assert runs[0]["listing_source"] == "fixture"


def test_listing_respects_limit() -> None:
    for _ in range(3):
        storage.save_run(_run_result(), "miamidade", "miamidade")
    assert len(storage.list_runs(limit=2)) == 2


def test_get_missing_run_raises_key_error() -> None:
    with pytest.raises(KeyError, match="no-such-run"):
        storage.get_run("no-such-run")
