import json
import urllib.parse

import httpx
import pytest

from app.providers import counties as counties_module
from app.providers import county_sources as sources_module
from app.providers.counties import CountyListingProvider, CountyParcelProvider
from app.providers.county_sources import (
    COLLIER,
    CLARK,
    MANATEE,
    MECKLENBURG,
)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    counties_module._cache.clear()
    sources_module._folio_year.clear()


def _feature(attrs: dict, centroid: tuple[float, float] | None = None) -> dict:
    feature = {"attributes": attrs}
    if centroid:
        feature["centroid"] = {"x": centroid[1], "y": centroid[0]}
    return feature


def _payload(features: list[dict]) -> dict:
    return {"features": features}


def _form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in urllib.parse.parse_qs(request.read().decode()).items()}


MANATEE_ATTRS = {
    "PARCEL_ID": "1234567890",
    "PRIMARY_ADDRESS": "112 OCEAN BLVD",
    "PROP_CITYNAME": "ANNA MARIA",
    "PROP_ZIP": "34216",
    "LAT": 27.4842,
    "LON": -82.7386,
    "YRBLT_RES": 1955,
    "JUSTVAL": 1_800_000,
    "ACRES": 0.31,
    "OWNER": "CITIZEN JANE",
}


def test_manatee_bulk_anchors_parse_and_filter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        form = _form(request)
        assert form["where"] == "PROP_CITYNAME IN ('ANNA MARIA','BRADENTON BEACH','HOLMES BEACH')"
        new = _feature(
            {**MANATEE_ATTRS, "PARCEL_ID": "A1", "YRBLT_RES": 2024, "JUSTVAL": 16_000_000}
        )
        old = _feature({**MANATEE_ATTRS, "PARCEL_ID": "A2", "YRBLT_RES": 1962})
        return httpx.Response(200, json=_payload([new, old]))

    anchors = CountyListingProvider(MANATEE, transport=httpx.MockTransport(handler)).fetch_anchors(
        MANATEE.market, min_price=15_000_000, min_year_built=2023
    )

    assert [a.parcel_id for a in anchors] == ["A1"]
    anchor = anchors[0]
    assert anchor.price == 16_000_000
    assert anchor.year_built == 2024
    assert anchor.state == "FL"
    assert anchor.city == "Anna Maria"


def test_manatee_parcels_radius_filter_in_memory() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        near = _feature({**MANATEE_ATTRS, "PARCEL_ID": "P1"})
        far = _feature({**MANATEE_ATTRS, "PARCEL_ID": "P2", "LAT": 27.5000})  # ~0.8mi out
        return httpx.Response(200, json=_payload([near, far]))

    parcels = CountyParcelProvider(MANATEE, transport=httpx.MockTransport(handler)).fetch_parcels_near(
        MANATEE.market, lat=27.4842, lon=-82.7386, radius_ft=500
    )

    assert [p.parcel_id for p in parcels] == ["P1"]
    parcel = parcels[0]
    assert parcel.estimated_value == 1_800_000
    assert parcel.year_built == 1955
    assert parcel.owner_name == "CITIZEN JANE"
    assert parcel.city == "Anna Maria"


COLLIER_ATTRS = {
    "FOLIO": "17410600106",
    "FULLADDRESS": "3333 RUM ROW",
    "NAME1": "CROWN, ROBERT A=& BARBARA A",
    "USECODE": "1",
    "TOTALACRES": "1.48",
    "TOTALJUSTAMOUNT": "53397116",
}


def test_collier_bulk_rows_enriched_with_statewide_year_built() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "collier" in url or "CityViewDesktop" in url:
            form = _form(request)
            assert form["where"] == "LEGALDESC LIKE '%PORT ROYAL%'"
            assert form["returnCentroid"] == "true"
            modern = _feature(
                {**COLLIER_ATTRS, "FOLIO": "C1", "TOTALJUSTAMOUNT": "20000000"},
                centroid=(26.1089, -81.7926),
            )
            older = _feature(
                {**COLLIER_ATTRS, "FOLIO": "C2", "TOTALJUSTAMOUNT": "9000000"},
                centroid=(26.1089, -81.7926),
            )
            non_sf = _feature({**COLLIER_ATTRS, "FOLIO": "C3", "USECODE": "6"})
            return httpx.Response(200, json=_payload([modern, older, non_sf]))
        # statewide cadastral enrichment
        form = _form(request)
        assert "PARCEL_ID IN" in form["where"]
        assert "ACT_YR_BLT" in form["outFields"]
        return httpx.Response(
            200,
            json=_payload(
                [
                    _feature({"PARCEL_ID": "C1", "ACT_YR_BLT": 2024}),
                    _feature({"PARCEL_ID": "C2", "ACT_YR_BLT": 1965}),
                ]
            ),
        )

    anchors = CountyListingProvider(COLLIER, transport=httpx.MockTransport(handler)).fetch_anchors(
        COLLIER.market, min_price=15_000_000, min_year_built=2023
    )

    assert [a.parcel_id for a in anchors] == ["C1"]  # C2 fails the year filter
    assert anchors[0].year_built == 2024
    assert anchors[0].city == "Naples"

    parcels = CountyParcelProvider(COLLIER, transport=httpx.MockTransport(handler)).fetch_parcels_near(
        COLLIER.market, lat=26.1089, lon=-81.7926, radius_ft=500
    )
    assert {p.parcel_id for p in parcels} == {"C1", "C2"}  # non-single-family skipped
    years = {p.parcel_id: p.year_built for p in parcels}
    assert years == {"C1": 2024, "C2": 1965}


MECK_ATTRS = {
    "pid": "12106C92",
    "yearbuilt": 2009,
    "totmarkval": 614_408.0,
    "ownrfrstnme": "WITOLD  M",
    "ownrlstnme": "BALAWEJDER",
    "address": "2204 LYNDHURST AV, TH21 CHARLOTTE NC",
    "city": "CHARLOTTE",
    "totalac": 1.0,
}


def test_mecklenburg_query_mode_anchors_and_envelope_parcels() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = _form(request)
        requests.append(form)
        if "yearbuilt>=" in form["where"]:
            assert form["where"] == "city='CHARLOTTE' AND yearbuilt>=2023 AND totmarkval>=15000000"
            assert json.loads(form["geometry"])["spatialReference"]["wkid"] == 4326
            return httpx.Response(
                200,
                json=_payload(
                    [
                        _feature({**MECK_ATTRS, "pid": "M1", "yearbuilt": 2024, "totmarkval": 16_000_000}, centroid=(35.205, -80.830)),
                        _feature({**MECK_ATTRS, "pid": "M1", "yearbuilt": 2020, "totmarkval": 5_000_000}, centroid=(35.205, -80.830)),  # dup pid card
                    ]
                ),
            )
        assert form["where"] == "city='CHARLOTTE'"
        return httpx.Response(
            200,
            json=_payload(
                [_feature({**MECK_ATTRS, "pid": "M2", "yearbuilt": 1958, "totmarkval": 900_000}, centroid=(35.205, -80.830))]
            ),
        )

    listing = CountyListingProvider(MECKLENBURG, transport=httpx.MockTransport(handler))
    anchors = listing.fetch_anchors(MECKLENBURG.market, min_price=15_000_000, min_year_built=2023)
    assert [a.parcel_id for a in anchors] == ["M1"]  # duplicate pid deduped
    assert anchors[0].year_built == 2024

    parcels = CountyParcelProvider(MECKLENBURG, transport=httpx.MockTransport(handler)).fetch_parcels_near(
        MECKLENBURG.market, lat=35.2050, lon=-80.8300, radius_ft=500
    )
    assert requests[-1]["geometryType"] == "esriGeometryEnvelope"
    assert len(parcels) == 1
    assert parcels[0].owner_name == "WITOLD M BALAWEJDER"
    assert parcels[0].city == "Charlotte"


CLARK_ATTRS = {
    "PARCEL": "12517713014",
    "OWNER": "ALLSHOUSE TODD ERIC",
    "CONSTYR": 2015,
    "LANDVAL1": 36_750,
    "IMPVAL": 97_111,
    "STRNO": 1061,
    "STRNAME": "VIA GANDALFI",
    "STRCITY": "HEND",
    "ZIP": 89011,
    "LOTSQFT": 1559,
}


def test_clark_anchor_where_and_parcels() -> None:
    def anchor_handler(request: httpx.Request) -> httpx.Response:
        form = _form(request)
        assert form["where"] == "(LANDVAL1+IMPVAL)>=15000000 AND CONSTYR>=2023 AND STRCITY IN ('LV','HEND')"
        return httpx.Response(
            200,
            json=_payload(
                [_feature({**CLARK_ATTRS, "CONSTYR": 2024, "LANDVAL1": 6_000_000, "IMPVAL": 9_000_000}, centroid=(36.02, -115.10))]
            ),
        )

    def parcel_handler(request: httpx.Request) -> httpx.Response:
        form = _form(request)
        assert form["where"] == "STRCITY IN ('LV','HEND')"
        assert form["geometryType"] == "esriGeometryEnvelope"
        populated = _feature({**CLARK_ATTRS}, centroid=(36.02, -115.10))
        blank_owner = _feature({**CLARK_ATTRS, "PARCEL": "X2", "OWNER": " "}, centroid=(36.02, -115.10))
        return httpx.Response(200, json=_payload([populated, blank_owner]))

    anchors = CountyListingProvider(CLARK, transport=httpx.MockTransport(anchor_handler)).fetch_anchors(
        CLARK.market, min_price=15_000_000, min_year_built=2023
    )
    assert anchors[0].price == 15_000_000
    assert anchors[0].year_built == 2024
    assert anchors[0].city == "Henderson"
    assert anchors[0].zip_code == "89011"

    parcels = CountyParcelProvider(CLARK, transport=httpx.MockTransport(parcel_handler)).fetch_parcels_near(
        CLARK.market, lat=36.02, lon=-115.10, radius_ft=500
    )
    assert len(parcels) == 2
    blank = next(p for p in parcels if p.parcel_id == "X2")
    assert blank.owner_name is None
    assert blank.estimated_value == 133_861
