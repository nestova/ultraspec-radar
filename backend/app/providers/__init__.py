from app.providers.attom import AttomParcelProvider, MissingCredentialsError
from app.providers.base import ListingProvider, ParcelProvider
from app.providers.fixture import (
    FixtureListingProvider,
    FixtureParcelProvider,
    available_markets,
)
from app.providers.tracerfy import TracerfyProvider


def get_listing_provider(name: str = "fixture") -> ListingProvider:
    if name == "fixture":
        return FixtureListingProvider()
    if name in ("tracerfy", "attom"):
        return TracerfyProvider()
    raise ValueError(f"Unknown listing provider '{name}'")


def get_parcel_provider(name: str = "fixture") -> ParcelProvider:
    if name == "fixture":
        return FixtureParcelProvider()
    if name in ("tracerfy", "attom"):
        return TracerfyProvider()
    raise ValueError(f"Unknown parcel provider '{name}'")


__all__ = [
    "AttomParcelProvider",
    "FixtureListingProvider",
    "FixtureParcelProvider",
    "ListingProvider",
    "MissingCredentialsError",
    "ParcelProvider",
    "TracerfyProvider",
    "available_markets",
    "get_listing_provider",
    "get_parcel_provider",
]
