import urllib.parse

import httpx
import pytest

from app.providers import maricopa as maricopa_module
from app.providers.maricopa import MARKET, MaricopaListingProvider, MaricopaParcelProvider


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    maricopa_module._cache.clear()


def _feature(attrs: dict) -> dict:
    return {"attributes": attrs}


def _payload(features: list[dict]) -> dict:
    return {"features": features}


BASE_ATTRS = {
    "APN": "16405085",
    "PHYSICAL_ADDRESS": "3301 E VALLEY VISTA LN   PARADISE VALLEY  85253",
    "PHYSICAL_CITY": "PARADISE VALLEY",
    "PHYSICAL_ZIP": "85253",
    "LATITUDE": 33.5334,
    "LONGITUDE": -111.9282,
    "CONST_YEAR": "2020",
    "FCV_CUR": "  10,500,000",
    "LAND_SIZE": 47737,
    "OWNER_NAME": "SMITH JOHN",
    "PUC": "0151",
}


def test_anchors_bulk_fetch_pv_and_parse_string_values() -> None:
    seen: dict = {}
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = urllib.parse.parse_qs(request.read().decode())
        seen["url"] = str(request.url)
        seen["form"] = form
        requests.append(form.get("resultOffset", ["0"])[0])
        new_build = _feature(
            {**BASE_ATTRS, "APN": "16405085", "CONST_YEAR": "2020", "FCV_CUR": "  10,500,000"}
        )
        old_build = _feature(
            {**BASE_ATTRS, "APN": "16644009", "CONST_YEAR": "1968", "FCV_CUR": "   3,200,000"}
        )
        # short page: pagination must stop after this single request
        return httpx.Response(200, json=_payload([new_build, old_build]))

    anchors = MaricopaListingProvider(transport=httpx.MockTransport(handler)).fetch_anchors(
        MARKET, min_price=8_000_000, min_year_built=2018
    )

    assert seen["url"].startswith("https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels")
    assert seen["form"]["where"][0] == "JURISDICTION='PARADISE VALLEY'"
    assert requests == ["0"]  # short page ends the bulk fetch
    assert len(anchors) == 1  # the 1968 parcel is excluded as an anchor
    anchor = anchors[0]
    assert anchor.price == 10_500_000  # comma-formatted string parsed to float
    assert anchor.year_built == 2020
    assert anchor.state == "AZ"
    assert anchor.parcel_id == "16405085"


def test_parcels_near_filters_by_radius_in_memory() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        near = _feature({**BASE_ATTRS, "APN": "16600001", "LATITUDE": 33.5334, "LONGITUDE": -111.9282})
        far = _feature(
            {
                **BASE_ATTRS,
                "APN": "16600002",
                "LATITUDE": 33.5450,  # ~0.8 miles away, past a 500 ft radius
                "LONGITUDE": -111.9282,
                "CONST_YEAR": "1968",
                "FCV_CUR": "   3,200,000",
            }
        )
        return httpx.Response(200, json=_payload([near, far]))

    parcels = MaricopaParcelProvider(transport=httpx.MockTransport(handler)).fetch_parcels_near(
        MARKET, lat=33.5334, lon=-111.9282, radius_ft=500
    )

    assert [p.parcel_id for p in parcels] == ["16600001"]
    parcel = parcels[0]
    assert parcel.estimated_value == 10_500_000
    assert parcel.lot_size_sqft == 47737
    assert parcel.owner_name == "SMITH JOHN"
    assert parcel.state == "AZ"


def test_parcels_skip_non_residential_and_missing_location() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        golf = _feature({**BASE_ATTRS, "APN": "16600003", "PUC": "0610"})
        noloc = _feature({**BASE_ATTRS, "APN": "16600004", "LATITUDE": None})
        return httpx.Response(200, json=_payload([golf, noloc]))

    parcels = MaricopaParcelProvider(transport=httpx.MockTransport(handler)).fetch_parcels_near(
        MARKET, lat=33.5334, lon=-111.9282, radius_ft=500
    )

    assert parcels == []
