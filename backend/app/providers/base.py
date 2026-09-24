from typing import Protocol, runtime_checkable

from app.models import AnchorHome, OwnerContact, Parcel


@runtime_checkable
class ListingProvider(Protocol):
    """Source of new-construction ultra-luxury listings/sales."""

    name: str

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        ...


@runtime_checkable
class ParcelProvider(Protocol):
    """Source of parcel geometry, valuation and ownership-of-record."""

    name: str

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        ...


@runtime_checkable
class SkipTraceProvider(Protocol):
    """Skip-traces property owners to retrieve phone numbers and email addresses."""

    name: str

    def skip_trace(self, address: str, city: str, state: str, zip_code: str = "") -> OwnerContact:
        ...
