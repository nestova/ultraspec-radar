"""Developer buy-boxes and buyer matching.

The catalog mirrors the Nestova "Development Opportunities" workbook — one
buy-box per named developer, grouped by market. Every developer listed there
acquires teardowns on a LAND BASIS: they underwrite the finished home they
would build in that pocket, then pay up to the land basis that leaves their
required margin, per the workbook's guiding rule:

    developer pays up to:  pocket resale − build cost − 15–20% margin

Pocket resale is proxied by the cluster's average anchor price (the
new-construction comps the pipeline already found around the parcel).
Lot floors, basis bands and teardown-era cutoffs come from the workbook's
per-market calibration table.
"""

from dataclasses import dataclass

from app.models import DeveloperMatch, Parcel

LAND_SHARE_CAP = 0.65  # even in teardown pockets, land is ≤ ~2/3 of finished value
MAX_MATCHES = 3


@dataclass(frozen=True)
class DeveloperBuyBox:
    name: str
    market: str
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
    # ————— Miami-Dade, FL (live data pilot) —————
    DeveloperBuyBox(
        name="Todd Michael Glaser",
        market="miami-dade-fl",
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
        market="miami-dade-fl",
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
        market="miami-dade-fl",
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
        market="miami-dade-fl",
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
        market="miami-dade-fl",
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
    # ————— Paradise Valley, AZ —————
    DeveloperBuyBox(
        name="Stately Development",
        market="paradise-valley-az",
        focus="One-acre-min teardown market; land-only $2–3M is the core buy-box",
        min_lot_sqft=43_560,
        homesite_lot_sqft=43_560,
        new_home_sqft=7_000,
        build_cost_psf=450,
        margin=0.18,
        aggressiveness=0.90,
        min_basis=1_500_000,
        max_basis=3_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Norton Luxury Homes",
        market="paradise-valley-az",
        focus="Flat buildable ~1-acre teardown lots ringed by $15M+ estates",
        min_lot_sqft=43_560,
        homesite_lot_sqft=43_560,
        new_home_sqft=7_000,
        build_cost_psf=450,
        margin=0.18,
        aggressiveness=0.88,
        min_basis=1_500_000,
        max_basis=3_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Thomas James Homes",
        market="paradise-valley-az",
        focus="Trophy ridgeline / larger-scale homesites (Mummy Mtn, Invergordon-type)",
        min_lot_sqft=43_560,
        homesite_lot_sqft=87_120,
        new_home_sqft=9_000,
        build_cost_psf=500,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=2_000_000,
        max_basis=10_000_000,
        max_year_built=1970,
    ),
    # ————— Los Angeles: Bel Air / Beverly Hills, CA —————
    DeveloperBuyBox(
        name="Nile Niami",
        market="bel-air-beverly-hills-ca",
        focus="$10M+ trophy sites; ultra-spec estate product",
        min_lot_sqft=15_000,
        homesite_lot_sqft=20_000,
        new_home_sqft=15_000,
        build_cost_psf=850,
        margin=0.20,
        aggressiveness=0.88,
        min_basis=10_000_000,
        max_basis=None,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Bruce Makowsky",
        market="bel-air-beverly-hills-ca",
        focus="$10M+ view sites for ultra-spec resale product",
        min_lot_sqft=15_000,
        homesite_lot_sqft=20_000,
        new_home_sqft=12_000,
        build_cost_psf=800,
        margin=0.20,
        aggressiveness=0.88,
        min_basis=10_000_000,
        max_basis=None,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Luxford Group (Michael Chen)",
        market="bel-air-beverly-hills-ca",
        focus="Prestige-block lots with plans/RTI included",
        min_lot_sqft=15_000,
        homesite_lot_sqft=20_000,
        new_home_sqft=10_000,
        build_cost_psf=700,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=4_000_000,
        max_basis=15_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Arya Group (Ardie Tavangarian)",
        market="bel-air-beverly-hills-ca",
        focus="Estate-section lots; assemblages a plus",
        min_lot_sqft=15_000,
        homesite_lot_sqft=25_000,
        new_home_sqft=12_000,
        build_cost_psf=750,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=4_000_000,
        max_basis=15_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Blackbriar",
        market="bel-air-beverly-hills-ca",
        focus="RTI / permitted $4M–$15M sites (entitlement risk already cut)",
        min_lot_sqft=15_000,
        homesite_lot_sqft=20_000,
        new_home_sqft=10_000,
        build_cost_psf=700,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=4_000_000,
        max_basis=15_000_000,
        max_year_built=1970,
    ),
    # ————— Naples: Port Royal, FL —————
    DeveloperBuyBox(
        name="Stock Custom Homes",
        market="port-royal-naples-fl",
        focus="Lot-and-a-half Port Royal homesites; Club-eligible blocks",
        min_lot_sqft=20_000,
        homesite_lot_sqft=30_000,
        new_home_sqft=8_000,
        build_cost_psf=550,
        margin=0.18,
        aggressiveness=0.88,
        min_basis=5_000_000,
        max_basis=None,
        max_year_built=1990,
    ),
    DeveloperBuyBox(
        name="London Bay Homes",
        market="port-royal-naples-fl",
        focus="Port Royal building assemblages; wide-water western exposure premium",
        min_lot_sqft=20_000,
        homesite_lot_sqft=30_000,
        new_home_sqft=8_500,
        build_cost_psf=550,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=5_000_000,
        max_basis=30_000_000,
        max_year_built=1990,
    ),
    DeveloperBuyBox(
        name="VIV Homes",
        market="port-royal-naples-fl",
        focus="Royal Harbor / adjacent open-bay entry into the Port Royal market",
        min_lot_sqft=10_000,
        homesite_lot_sqft=15_000,
        new_home_sqft=6_000,
        build_cost_psf=450,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=2_000_000,
        max_basis=15_000_000,
        max_year_built=1990,
    ),
    # ————— Bradenton Beach / Anna Maria Island, FL —————
    DeveloperBuyBox(
        name="Issa Homes",
        market="bradenton-anna-maria-fl",
        focus="Gulf-front teardowns and permitted beachfront homesites (DEP permit in hand)",
        min_lot_sqft=5_000,
        homesite_lot_sqft=8_000,
        new_home_sqft=4_500,
        build_cost_psf=500,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=3_000_000,
        max_basis=15_000_000,
        max_year_built=1990,
    ),
    DeveloperBuyBox(
        name="Perrone",
        market="bradenton-anna-maria-fl",
        focus="Estate-sized Gulf-front lots (100'+ beachfront)",
        min_lot_sqft=10_000,
        homesite_lot_sqft=20_000,
        new_home_sqft=6_000,
        build_cost_psf=550,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=3_000_000,
        max_basis=25_000_000,
        max_year_built=1990,
    ),
    DeveloperBuyBox(
        name="Blue Crane",
        market="bradenton-anna-maria-fl",
        focus="Beachfront teardown / cleared-lot plays near Bridge St",
        min_lot_sqft=5_000,
        homesite_lot_sqft=8_000,
        new_home_sqft=4_000,
        build_cost_psf=450,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=1_500_000,
        max_basis=8_000_000,
        max_year_built=1990,
    ),
    DeveloperBuyBox(
        name="Dospel",
        market="bradenton-anna-maria-fl",
        focus="Sizeable luxury residential redevelopment tracts / gated enclaves",
        min_lot_sqft=43_560,
        homesite_lot_sqft=87_120,
        new_home_sqft=6_000,
        build_cost_psf=500,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=2_000_000,
        max_basis=20_000_000,
        max_year_built=1990,
    ),
    # ————— Las Vegas / Henderson, NV —————
    DeveloperBuyBox(
        name="Heritage Homes",
        market="las-vegas-henderson-nv",
        focus="Guard-gated hillside homesites (Ascaya / MacDonald Highlands) with Strip views",
        min_lot_sqft=21_780,
        homesite_lot_sqft=21_780,
        new_home_sqft=6_000,
        build_cost_psf=400,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=1_000_000,
        max_basis=18_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="LIVV Homes",
        market="las-vegas-henderson-nv",
        focus="Half-acre-plus developer homesites; custom luxury product",
        min_lot_sqft=21_780,
        homesite_lot_sqft=21_780,
        new_home_sqft=6_500,
        build_cost_psf=420,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=1_000_000,
        max_basis=18_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Christopher Homes",
        market="las-vegas-henderson-nv",
        focus="Estate-scale hillside lots; Dragon Ridge / Ascaya pockets",
        min_lot_sqft=21_780,
        homesite_lot_sqft=43_560,
        new_home_sqft=7_000,
        build_cost_psf=450,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=1_000_000,
        max_basis=18_000_000,
        max_year_built=1970,
    ),
    DeveloperBuyBox(
        name="Blue Heron",
        market="las-vegas-henderson-nv",
        focus="Modern hillside view homesites (Ascaya-type, Strip-view orientation)",
        min_lot_sqft=21_780,
        homesite_lot_sqft=21_780,
        new_home_sqft=6_000,
        build_cost_psf=450,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=2_000_000,
        max_basis=18_000_000,
        max_year_built=1970,
    ),
    # ————— The Hamptons, NY —————
    DeveloperBuyBox(
        name="Jeffrey Colle",
        market="hamptons-ny",
        focus="Deep-water dockage compounds and waterfront assemblages",
        min_lot_sqft=87_120,
        homesite_lot_sqft=130_680,
        new_home_sqft=10_000,
        build_cost_psf=800,
        margin=0.20,
        aggressiveness=0.85,
        min_basis=5_000_000,
        max_basis=None,
        max_year_built=1980,
    ),
    DeveloperBuyBox(
        name="Konner Development",
        market="hamptons-ny",
        focus="Village-fringe flat estate lots; spec-estate canvas",
        min_lot_sqft=43_560,
        homesite_lot_sqft=87_120,
        new_home_sqft=8_000,
        build_cost_psf=650,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=3_000_000,
        max_basis=20_000_000,
        max_year_built=1980,
    ),
    DeveloperBuyBox(
        name="South Fork",
        market="hamptons-ny",
        focus="Permitted / buildable bay-view parcels (NRSP in hand)",
        min_lot_sqft=43_560,
        homesite_lot_sqft=87_120,
        new_home_sqft=7_500,
        build_cost_psf=600,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=3_000_000,
        max_basis=15_000_000,
        max_year_built=1980,
    ),
    # ————— Seattle Eastside: Medina / Hunts Point, WA —————
    DeveloperBuyBox(
        name="Mirikeen Homes",
        market="seattle-eastside-wa",
        focus="Medina / Hunts Point teardowns — the rebuild path where vacant land is absent",
        min_lot_sqft=10_000,
        homesite_lot_sqft=15_000,
        new_home_sqft=6_500,
        build_cost_psf=550,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=3_000_000,
        max_basis=25_000_000,
        max_year_built=1980,
    ),
    DeveloperBuyBox(
        name="John Buchan Homes",
        market="seattle-eastside-wa",
        focus="Oversized Medina teardown parcels and waterfront estates",
        min_lot_sqft=10_000,
        homesite_lot_sqft=15_000,
        new_home_sqft=6_000,
        build_cost_psf=550,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=3_000_000,
        max_basis=20_000_000,
        max_year_built=1980,
    ),
    # ————— Atherton / Silicon Valley, CA —————
    DeveloperBuyBox(
        name="Private land-value buyers (Atherton)",
        market="atherton-ca",
        focus="Land-value market — private end-users bid up ~1-acre teardowns; almost all value is land",
        min_lot_sqft=43_560,
        homesite_lot_sqft=43_560,
        new_home_sqft=8_000,
        build_cost_psf=700,
        margin=0.18,
        aggressiveness=0.80,
        min_basis=5_000_000,
        max_basis=None,
        max_year_built=1970,
    ),
    # ————— Charlotte: Myers Park / Eastover, NC —————
    DeveloperBuyBox(
        name="Peters Custom Homes",
        market="charlotte-nc",
        focus="Myers Park teardown-rebuild on Olmsted premier streets",
        min_lot_sqft=8_000,
        homesite_lot_sqft=13_000,
        new_home_sqft=5_000,
        build_cost_psf=350,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=1_000_000,
        max_basis=3_000_000,
        max_year_built=1960,
    ),
    DeveloperBuyBox(
        name="Everett Custom Homes",
        market="charlotte-nc",
        focus="Eastover / Myers Park old-home teardowns for $3M+ new builds",
        min_lot_sqft=8_000,
        homesite_lot_sqft=13_000,
        new_home_sqft=5_000,
        build_cost_psf=350,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=1_000_000,
        max_basis=3_000_000,
        max_year_built=1960,
    ),
    DeveloperBuyBox(
        name="Andrew Signature Homes",
        market="charlotte-nc",
        focus="Teardown-rebuild sites priced near land value on premier streets",
        min_lot_sqft=8_000,
        homesite_lot_sqft=13_000,
        new_home_sqft=5_500,
        build_cost_psf=350,
        margin=0.18,
        aggressiveness=0.85,
        min_basis=1_000_000,
        max_basis=3_000_000,
        max_year_built=1960,
    ),
)


def developer_names(market: str) -> list[str]:
    """Names of the developers whose buy-boxes cover a market."""
    return [d.name for d in DEVELOPERS if d.market == market]


def max_land_basis(dev: DeveloperBuyBox, pocket_resale: float) -> float:
    """Theoretical max land spend: resale − build − margin."""
    build_cost = dev.new_home_sqft * dev.build_cost_psf
    budget = pocket_resale - build_cost - pocket_resale * dev.margin
    return max(budget, 0.0)


def match_developers(parcel: Parcel, avg_anchor_price: float, market: str) -> list[DeveloperMatch]:
    """Screen a candidate parcel against the buy-boxes active in its market.

    Returns the matching developers (best fit first) with the dollar amount
    each could pay for the land while keeping their margin.
    """
    lot = parcel.lot_size_sqft or 0.0
    resale = max(avg_anchor_price, 0.0)
    current_value = parcel.estimated_value or 0.0

    matches: list[DeveloperMatch] = []
    for dev in DEVELOPERS:
        if dev.market != market:
            continue
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
