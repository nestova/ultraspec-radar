import os

from app.models import AnchorHome, Parcel


class MissingCredentialsError(RuntimeError):
    pass


class AttomParcelProvider:
    """Licensed ATTOM Data adapter.

    Intentionally the production path for valuation and ownership: the PRD rules
    out direct Zillow scraping. Requires ATTOM_API_KEY.
    """

    name = "attom"
    base_url = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("ATTOM_API_KEY")

    def _require_key(self) -> str:
        if not self.api_key:
            raise MissingCredentialsError(
                "ATTOM_API_KEY is not set. Configure a licensed data source or use the fixture provider."
            )
        return self.api_key

    def fetch_anchors(self, market: str, min_price: float, min_year_built: int) -> list[AnchorHome]:
        self._require_key()
        raise NotImplementedError("ATTOM listing ingestion is wired up once a license key is provisioned.")

    def fetch_parcels_near(self, market: str, lat: float, lon: float, radius_ft: float) -> list[Parcel]:
        self._require_key()
        raise NotImplementedError("ATTOM parcel ingestion is wired up once a license key is provisioned.")
