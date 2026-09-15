import httpx
import pytest

from app.providers import miamidade as miamidade_module
from app.providers.miamidade import (
    MARKET,
    MiamiDadeListingProvider,
    MiamiDadeParcelProvider,
    ProviderUnavailableError,
)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    miamidade_module._cache.clear()


def _feature(attrs: dict, lat: float = 25.87, lon: float = -80.13) -> dict:
    return {"attributes": attrs, "geometry": {"x": lon, "y": lat}}


def _transport(payload: dict) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json=payload))


def test_anchors_query_the_appraiser_layer_and_map_fields() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["form"] = dict(item.split("=", 1) for item in request.read().decode().split("&"))
        return httpx.Response(
            200,
            json={
                "features": [
                    _feature(
                        {
                            "FOLIO": "2122340020250",
                            "TRUE_SITE_ADDR": "26 INDIAN CREEK ISLAND RD",
                            "TRUE_SITE_CITY": "Indian Creek",
                            "TRUE_SITE_ZIP_CODE": "33154",
                            "YEAR_BUILT": 2024,
                            "ASSESSED_VAL_CUR": 99684916,
                        }
                    )
                ]
            },
        )

    anchors = MiamiDadeListingProvider(transport=httpx.MockTransport(handler)).fetch_anchors(
        MARKET, min_price=15_000_000, min_year_built=2023
    )

    assert "PaGISView_gdb/FeatureServer/0/query" in seen["url"]
    assert "DOR_CODE_CUR+%3D+%270101%27" in seen["form"]["where"]
    assert "YEAR_BUILT+%3E%3D+2023" in seen["form"]["where"]
    assert "ASSESSED_VAL_CUR+%3E%3D+15000000" in seen["form"]["where"]

    assert len(anchors) == 1
    anchor = anchors[0]
    assert anchor.id == "2122340020250"
    assert anchor.parcel_id == "2122340020250"
    assert anchor.address == "26 INDIAN CREEK ISLAND RD"
    assert anchor.city == "Indian Creek"
    assert anchor.state == "FL"
    assert anchor.price == 99_684_916.0
    assert anchor.year_built == 2024
    assert anchor.status == "sold"
    assert (anchor.lat, anchor.lon) == (25.87, -80.13)
    assert anchor.provenance.source.startswith("Miami-Dade Property Appraiser")


def test_anchors_apply_min_price_and_year_filters_in_python_too() -> None:
    payload = {
        "features": [
            _feature({"FOLIO": "1", "YEAR_BUILT": 2024, "ASSESSED_VAL_CUR": 20_000_000}),
            _feature({"FOLIO": "2", "YEAR_BUILT": 2022, "ASSESSED_VAL_CUR": 50_000_000}),
        ]
    }
    anchors = MiamiDadeListingProvider(transport=_transport(payload)).fetch_anchors(
        MARKET, min_price=15_000_000, min_year_built=2023
    )
    assert [a.id for a in anchors] == ["1"]


def test_parcels_near_maps_fields_and_joins_owners() -> None:
    payload = {
        "features": [
            _feature(
                {
                    "FOLIO": "2122340020240",
                    "TRUE_SITE_ADDR": "25 INDIAN CREEK ISLAND RD",
                    "TRUE_SITE_CITY": "Indian Creek",
                    "TRUE_SITE_ZIP_CODE": "33154",
                    "TRUE_OWNER1": "ITZHAK EZRATTI",
                    "TRUE_OWNER2": None,
                    "TRUE_OWNER3": "",
                    "YEAR_BUILT": 2006,
                    "ASSESSED_VAL_CUR": 16_646_659,
                    "LOT_SIZE": 80000,
                },
                lat=25.8738,
                lon=-80.1355,
            ),
            _feature(
                {
                    "FOLIO": "2122340020230",
                    "TRUE_SITE_ADDR": "24 INDIAN CREEK ISLAND RD",
                    "TRUE_SITE_CITY": "Indian Creek",
                    "TRUE_SITE_ZIP_CODE": "33154",
                    "TRUE_OWNER1": "CARL C ICAHN TRS",
                    "TRUE_OWNER2": "SECOND OWNER",
                    "TRUE_OWNER3": None,
                    "YEAR_BUILT": None,
                    "ASSESSED_VAL_CUR": None,
                    "LOT_SIZE": None,
                }
            ),
        ]
    }
    parcels = MiamiDadeParcelProvider(transport=_transport(payload)).fetch_parcels_near(
        MARKET, lat=25.874, lon=-80.135, radius_ft=500
    )

    assert len(parcels) == 2
    first, second = parcels
    assert first.parcel_id == "2122340020240"
    assert first.year_built == 2006
    assert first.estimated_value == 16_646_659.0
    assert first.lot_size_sqft == 80000.0
    assert first.owner_name == "ITZHAK EZRATTI"
    assert first.assessor_url == "https://apps.miamidadepa.gov/PropertySearch/"
    assert second.year_built is None
    assert second.estimated_value is None
    assert second.lot_size_sqft is None
    assert second.owner_name == "CARL C ICAHN TRS SECOND OWNER"


def test_error_payload_raises_provider_unavailable() -> None:
    transport = _transport({"error": {"code": 400, "message": "Invalid query"}})
    with pytest.raises(ProviderUnavailableError):
        MiamiDadeListingProvider(transport=transport).fetch_anchors(MARKET, 15_000_000, 2023)


def test_http_failure_raises_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(ProviderUnavailableError):
        MiamiDadeParcelProvider(transport=httpx.MockTransport(handler)).fetch_parcels_near(
            MARKET, 25.8, -80.1, 500
        )


def test_unsupported_market_raises_value_error() -> None:
    with pytest.raises(ValueError, match="miami-dade-fl"):
        MiamiDadeListingProvider().fetch_anchors("los-angeles-ca", 15_000_000, 2023)
    with pytest.raises(ValueError, match="miami-dade-fl"):
        MiamiDadeParcelProvider().fetch_parcels_near("los-angeles-ca", 25.8, -80.1, 500)
