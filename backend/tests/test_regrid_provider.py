import urllib.parse

import httpx
import pytest

from app.providers import regrid as regrid_module
from app.providers.attom import MissingCredentialsError
from app.providers.regrid import (
    RegridListingProvider,
    RegridParcelProvider,
)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    regrid_module._cache.clear()
    regrid_module._fetched_parcels = 0
    regrid_module._quota_warned = False


def _params(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in urllib.parse.parse_qs(request.url.query.decode()).items()}


def _feature(fid: int, props: dict) -> dict:
    # API v2 nests the standard-schema attributes under properties.fields
    return {"id": fid, "type": "Feature", "properties": {"fields": props, "ll_uuid": f"uuid-{fid}"}}


def _payload(features: list[dict]) -> dict:
    return {"parcels": {"type": "FeatureCollection", "features": features}}


BASE_PROPS = {
    "parcelnumb": "APN-1",
    "address": "100 ISABELLA AVENUE",
    "scity": "ATHERTON",
    "szip": "94027",
    "lat": "37.4550",
    "lon": "-122.1980",
    "yearbuilt": 2024,
    "ll_gissqft": 30000,
    "parval": 9_500_000,
    "owner": "SMITH FAMILY TRUST",
}


def test_missing_token_raises_credentials_error(monkeypatch) -> None:
    monkeypatch.delenv("REGRID_API_TOKEN", raising=False)
    with pytest.raises(MissingCredentialsError):
        RegridListingProvider(token=None).fetch_anchors("atherton-ca", 5_000_000, 2023)


def test_rejected_token_raises_credentials_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid token"})

    with pytest.raises(MissingCredentialsError):
        RegridListingProvider(
            token="t", transport=httpx.MockTransport(handler)
        ).fetch_anchors("atherton-ca", 5_000_000, 2023)


def test_unknown_market_raises() -> None:
    with pytest.raises(ValueError):
        RegridListingProvider(token="t").fetch_anchors("miami-dade-fl", 5_000_000, 2023)


def test_anchors_query_filters_and_maps() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        assert params["token"] == "t"
        assert params["lat"] == "37.455"
        assert params["lon"] == "-122.198"
        assert params["radius"] == "3000"
        assert params["fields[yearbuilt][gte]"] == "2023"
        assert params["fields[ll_gissqft][gte]"] == "5000"
        assert params["return_geometry"] == "false"
        assert params["offset_id"] == "0"
        rich = _feature(1, dict(BASE_PROPS, parcelnumb="A1", parval=9_000_000))
        cheap = _feature(2, dict(BASE_PROPS, parcelnumb="A2", parval=900_000))
        return httpx.Response(200, json=_payload([rich, cheap]))

    anchors = RegridListingProvider(
        token="t", transport=httpx.MockTransport(handler)
    ).fetch_anchors("atherton-ca", min_price=5_000_000, min_year_built=2023)

    assert [a.parcel_id for a in anchors] == ["A1"]
    anchor = anchors[0]
    assert anchor.price == 9_000_000
    assert anchor.year_built == 2024
    assert anchor.address == "100 ISABELLA AVENUE"
    assert anchor.city == "ATHERTON"
    assert anchor.zip_code == "94027"
    assert anchor.state == "CA"
    assert anchor.provenance.source == "regrid"


def test_anchors_paginate_with_offset_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        if params["offset_id"] == "0":
            page = [_feature(i, dict(BASE_PROPS, parcelnumb=f"A{i}")) for i in range(1000)]
        else:
            assert params["offset_id"] == "999"
            page = [_feature(1000, dict(BASE_PROPS, parcelnumb="A1000"))]
        return httpx.Response(200, json=_payload(page))

    anchors = RegridListingProvider(
        token="t", transport=httpx.MockTransport(handler)
    ).fetch_anchors("atherton-ca", min_price=5_000_000, min_year_built=2023)

    assert len(anchors) == 1001


def test_parcels_near_maps_fields_and_respects_radius() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        assert params["lat"] == "37.455"
        assert params["lon"] == "-122.198"
        assert params["radius"] == str(int(500 * 0.3048))
        near = _feature(1, dict(BASE_PROPS, parcelnumb="P1"))
        far = _feature(2, dict(BASE_PROPS, parcelnumb="P2", lat="37.47", lon="-122.19"))
        return httpx.Response(200, json=_payload([near, far]))

    parcels = RegridParcelProvider(
        token="t", transport=httpx.MockTransport(handler)
    ).fetch_parcels_near("atherton-ca", 37.455, -122.198, radius_ft=500)

    assert [p.parcel_id for p in parcels] == ["P1"]
    parcel = parcels[0]
    assert parcel.owner_name == "SMITH FAMILY TRUST"
    assert parcel.estimated_value == 9_500_000
    assert parcel.lot_size_sqft == 30000
    assert parcel.year_built == 2024
    assert parcel.provenance.source == "regrid"


def test_features_without_coordinates_are_dropped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        bad = _feature(1, dict(BASE_PROPS, lat=None))
        good = _feature(2, dict(BASE_PROPS, parcelnumb="P2"))
        return httpx.Response(200, json=_payload([bad, good]))

    parcels = RegridParcelProvider(
        token="t", transport=httpx.MockTransport(handler)
    ).fetch_parcels_near("atherton-ca", 37.455, -122.198, radius_ft=500)

    assert [p.parcel_id for p in parcels] == ["P2"]
