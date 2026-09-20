from app.providers.attom import AttomParcelProvider, MissingCredentialsError
from app.providers.base import ListingProvider, ParcelProvider
from app.providers.counties import CountyListingProvider, CountyParcelProvider
from app.providers.county_sources import COUNTY_SOURCES
from app.providers.fixture import (
    FixtureListingProvider,
    FixtureParcelProvider,
    available_markets,
)
from app.providers.maricopa import (
    MaricopaListingProvider,
    MaricopaParcelProvider,
)
from app.providers.miamidade import (
    MiamiDadeListingProvider,
    MiamiDadeParcelProvider,
    ProviderUnavailableError,
)
from app.providers.regrid import (
    RegridListingProvider,
    RegridParcelProvider,
    REGRID_MARKETS,
)


def get_listing_provider(name: str = "fixture") -> ListingProvider:
    if name == "fixture":
        return FixtureListingProvider()
    if name == "miamidade":
        return MiamiDadeListingProvider()
    if name == "maricopa":
        return MaricopaListingProvider()
    if name in COUNTY_SOURCES:
        return CountyListingProvider(COUNTY_SOURCES[name])
    if name == "regrid":
        return RegridListingProvider()
    if name == "attom":
        return AttomParcelProvider()
    raise ValueError(f"Unknown listing provider '{name}'")


def get_parcel_provider(name: str = "fixture") -> ParcelProvider:
    if name == "fixture":
        return FixtureParcelProvider()
    if name == "miamidade":
        return MiamiDadeParcelProvider()
    if name == "maricopa":
        return MaricopaParcelProvider()
    if name in COUNTY_SOURCES:
        return CountyParcelProvider(COUNTY_SOURCES[name])
    if name == "regrid":
        return RegridParcelProvider()
    if name == "attom":
        return AttomParcelProvider()
    raise ValueError(f"Unknown parcel provider '{name}'")


__all__ = [
    "AttomParcelProvider",
    "RegridParcelProvider",
    "RegridListingProvider",
    "REGRID_MARKETS",
    "FixtureListingProvider",
    "FixtureParcelProvider",
    "ListingProvider",
    "MaricopaListingProvider",
    "MaricopaParcelProvider",
    "MiamiDadeListingProvider",
    "MiamiDadeParcelProvider",
    "MissingCredentialsError",
    "ParcelProvider",
    "ProviderUnavailableError",
    "available_markets",
    "get_listing_provider",
    "get_parcel_provider",
]
