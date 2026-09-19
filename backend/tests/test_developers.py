from datetime import datetime, timezone

from app.developers import DEVELOPERS, developer_names, match_developers, max_land_basis
from app.models import Parcel, Provenance

MARKET = "miami-dade-fl"


def _parcel(lot: float, value: float, year: int = 1955) -> Parcel:
    return Parcel(
        parcel_id="test-1",
        address="1 Test St",
        city="Miami",
        state="FL",
        zip_code="33139",
        lat=25.0,
        lon=-80.0,
        year_built=year,
        lot_size_sqft=lot,
        estimated_value=value,
        provenance=Provenance(source="test", retrieved_at=datetime.now(timezone.utc)),
    )


def test_offer_follows_the_buy_box_math():
    dev = DEVELOPERS[0]
    resale = 20_000_000
    expected_budget = resale - dev.new_home_sqft * dev.build_cost_psf - resale * dev.margin
    assert max_land_basis(dev, resale) == expected_budget


def test_every_market_in_the_registry_has_developers():
    from app.markets import market_ids

    for market_id in market_ids():
        names = developer_names(market_id)
        assert names, f"market {market_id} has no developer buy-boxes"


def test_big_old_lot_in_rich_pocket_matches_developers():
    parcel = _parcel(lot=15_000, value=1_500_000)
    matches = match_developers(parcel, avg_anchor_price=20_000_000, market=MARKET)
    assert matches
    top = matches[0]
    assert top.max_offer >= 1_500_000
    assert top.max_offer <= 20_000_000 * 0.65
    assert "sf build" in top.rationale
    # sorted best-fit first
    assert all(matches[i].fit >= matches[i + 1].fit for i in range(len(matches) - 1))


def test_matches_are_scoped_to_the_market():
    parcel = _parcel(lot=90_000, value=1_500_000)
    # a Miami buy-box developer never matches a Paradise Valley parcel
    miami_matches = match_developers(parcel, avg_anchor_price=20_000_000, market=MARKET)
    pv_matches = match_developers(parcel, avg_anchor_price=20_000_000, market="paradise-valley-az")
    assert {m.developer for m in miami_matches}.isdisjoint({m.developer for m in pv_matches})
    assert pv_matches  # PV buy-boxes (1-acre floor) do fit a 2-acre lot


def test_tiny_lot_is_below_every_buy_box():
    parcel = _parcel(lot=2_000, value=900_000)
    assert match_developers(parcel, avg_anchor_price=20_000_000, market=MARKET) == []


def test_new_home_is_not_a_teardown():
    parcel = _parcel(lot=15_000, value=1_500_000, year=2015)
    assert match_developers(parcel, avg_anchor_price=20_000_000, market=MARKET) == []


def test_overpriced_parcel_fails_the_land_basis():
    # current value already above what any developer could justify paying
    parcel = _parcel(lot=15_000, value=99_000_000)
    assert match_developers(parcel, avg_anchor_price=20_000_000, market=MARKET) == []
