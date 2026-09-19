"""Developer buy-boxes and buyer matching.

The catalog mirrors the Nestova "Development Opportunities" workbook
(Miami / South Florida section). Every developer listed there acquires
teardowns on a LAND BASIS: they underwrite the finished home they would
build in that pocket, then pay up to the land basis that leaves their
required margin, per the workbook's guiding rule:

    developer pays up to:  pocket resale − build cost − 15–20% margin

Pocket resale is proxied by the cluster's average anchor price (the
new-construction comps the pipeline already found around the parcel).
"""

from dataclasses import dataclass

from app.models import DeveloperMatch, Parcel

LAND_SHARE_CAP = 0.65  # even in teardown pockets, land is ≤ ~2/3 of finished value
MAX_MATCHES = 3


@dataclass(frozen=True)
class DeveloperBuyBox:
    name: str
    focus: str
    min_lot_sqft: float  # buy-box floor — smaller lots are a different product
    homesite_lot_sqft: float  # lot size their spec home assumes; offers scale below this
    new_home_sqft: float
    build_cost_psf: float
    margin: float  # required developer margin on finished resale
    aggressiveness: float  # share of the theoretical max basis they'd actually pay
    min_basis: float  # smallest land purchase they'll chase
    max_basis: float | None  # largest (None = land-basis driven, no cap)
    max_year_built: int  # teardown-era cutoff for the existing structure


DEVELOPERS: tuple[DeveloperBuyBox, ...] = (
    DeveloperBuyBox(
        name="Todd Michael Glaser",
        focus="Ultra-trophy waterfront teardowns & assemblages (Palm Beach Estate Section, oceanfront)",
        min_lot_sqft=9_000,
        homesite_lot_sqft=15_000,
        new_home_sqft=10_000,
        build_cost_psf=700,
        margin=0.20,
        aggressiveness=0.90,
        min_basis=5_000_000,
        max_basis=None,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Keith Menin",
        focus="Prime Miami Beach teardowns (North Bay Rd-type: 1950s house, land carries the value)",
        min_lot_sqft=6_000,
        homesite_lot_sqft=9_000,
        new_home_sqft=8_000,
        build_cost_psf=600,
        margin=0.18,
        aggressiveness=0.90,
        min_basis=1_500_000,
        max_basis=30_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Mosie Miller",
        focus="Miami Beach waterfront teardowns underwritten on land basis",
        min_lot_sqft=9_000,
        homesite_lot_sqft=12_000,
        new_home_sqft=9_000,
        build_cost_psf=650,
        margin=0.18,
        aggressiveness=0.88,
        min_basis=5_000_000,
        max_basis=50_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="SRD Building",
        focus="Gated-island scale waterfront sites (Hibiscus/Palm Island-type)",
        min_lot_sqft=10_000,
        homesite_lot_sqft=12_000,
        new_home_sqft=9_000,
        build_cost_psf=600,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=3_000_000,
        max_basis=25_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Luis Bosch",
        focus="Gated island frontage teardowns (Sunset Islands / Golden Beach-type)",
        min_lot_sqft=5_000,
        homesite_lot_sqft=7_500,
        new_home_sqft=7_000,
        build_cost_psf=550,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=1_000_000,
        max_basis=15_000_000,
        max_year_built=1970,
    ),
)


def max_land_basis(dev: DeveloperBuyBox, pocket_resale: float) -> float:
    """Theoretical max land spend: resale − build − margin, capped by land share."""
    build_cost = dev.new_home_sqft * dev.build_cost_psf
    budget = pocket_resale - build_cost - pocket_resale * dev.margin
    return max(budget, 0.0)


def match_developers(parcel: Parcel, avg_anchor_price: float) -> list[DeveloperMatch]:
    """Screen a candidate parcel against every developer buy-box.

    Returns the matching developers (best fit first) with the dollar amount
    each could pay for the land while keeping their margin.
    """
    lot = parcel.lot_size_sqft or 0.0
    resale = max(avg_anchor_price, 0.0)
    current_value = parcel.estimated_value or 0.0

    matches: list[DeveloperMatch] = []
    for dev in DEVELOPERS:
        if (parcel.year_built or 0) > dev.max_year_built:
            continue
        if lot < dev.min_lot_sqft:
            continue

        offer = max_land_basis(dev, resale)
        lot_factor = min(max(lot / dev.homesite_lot_sqft, 0.25), 1.0)
        offer = offer * lot_factor * dev.aggressiveness
        offer = min(offer, resale * LAND_SHARE_CAP)
        if dev.max_basis is not None:
            offer = min(offer, dev.max_basis)
        offer = round(offer, 2)

        if offer < dev.min_basis:
            continue
        if current_value > offer:
            # acquisition already sits above this developer's land basis
            continue

        upside = (offer - current_value) / offer if offer else 0.0
        lot_fit = min(lot / dev.min_lot_sqft, 1.0) if dev.min_lot_sqft else 1.0
        fit = round(0.5 * lot_fit + 0.5 * upside, 4)
        rationale = (
            f"Teardown-era {parcel.year_built} home on a {lot:,.0f} sf lot in a "
            f"~${resale / 1e6:.1f}M pocket. Offer = pocket resale − "
            f"{dev.new_home_sqft:,} sf build @ ${dev.build_cost_psf}/sf − "
            f"{dev.margin:.0%} margin, scaled to lot size."
        )
        matches.append(
            DeveloperMatch(
                developer=dev.name,
                fit=fit,
                max_offer=offer,
                rationale=rationale,
            )
        )

    matches.sort(key=lambda m: (-m.fit, -m.max_offer))
    return matches[:MAX_MATCHES]
