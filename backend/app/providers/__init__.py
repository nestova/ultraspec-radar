from app.providers.attom import AttomParcelProvider, MissingCredentialsError
from app.providers.base import ListingProvider, ParcelProvider, SkipTraceProvider
from app.providers.fixture import (
    FixtureListingProvider,
    FixtureParcelProvider,
    available_markets,
)
from app.providers.miami_dade import MiamiDadeListingProvider, MiamiDadeParcelProvider
from app.providers.tracerfy import TracerfyProvider


def get_listing_provider(name: str = "miami-dade") -> ListingProvider:
    if name == "miami-dade":
        return MiamiDadeListingProvider()
    if name == "fixture":
        return FixtureListingProvider()
    raise ValueError(f"Unknown listing provider '{name}'")


def get_parcel_provider(name: str = "miami-dade") -> ParcelProvider:
    if name == "miami-dade":
        return MiamiDadeParcelProvider()
    if name == "fixture":
        return FixtureParcelProvider()
    raise ValueError(f"Unknown parcel provider '{name}'")


def get_skip_trace_provider(name: str = "tracerfy") -> SkipTraceProvider:
    if name == "tracerfy":
        return TracerfyProvider()
    raise ValueError(f"Unknown skip-trace provider '{name}'")


__all__ = [
    "AttomParcelProvider",
    "FixtureListingProvider",
    "FixtureParcelProvider",
    "ListingProvider",
    "MiamiDadeListingProvider",
    "MiamiDadeParcelProvider",
    "MissingCredentialsError",
    "ParcelProvider",
    "SkipTraceProvider",
    "TracerfyProvider",
    "available_markets",
    "get_listing_provider",
    "get_parcel_provider",
    "get_skip_trace_provider",
]
