from app.providers.attom import AttomParcelProvider, MissingCredentialsError
from app.providers.base import ListingProvider, ParcelProvider, SkipTraceProvider
from app.providers.fixture import (
    FixtureListingProvider,
    FixtureParcelProvider,
    available_markets,
)
from app.providers.tracerfy import TracerfyProvider


def get_listing_provider(name: str = "fixture") -> ListingProvider:
    if name == "fixture":
        return FixtureListingProvider()
    raise ValueError(f"Unknown listing provider '{name}'")


def get_parcel_provider(name: str = "fixture") -> ParcelProvider:
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
    "MissingCredentialsError",
    "ParcelProvider",
    "SkipTraceProvider",
    "TracerfyProvider",
    "available_markets",
    "get_listing_provider",
    "get_parcel_provider",
    "get_skip_trace_provider",
]
