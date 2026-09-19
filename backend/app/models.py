from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Provenance(BaseModel):
    source: str
    source_url: str | None = None
    retrieved_at: datetime


class AnchorHome(BaseModel):
    """A new-construction ultra-luxury home used as a cluster anchor."""

    id: str
    address: str
    city: str
    state: str
    zip_code: str
    lat: float
    lon: float
    price: float
    status: Literal["listed", "under_contract", "sold"]
    year_built: int
    builder: str | None = None
    parcel_id: str | None = None
    listing_url: str | None = None
    provenance: Provenance


class Parcel(BaseModel):
    """A parcel neighboring an anchor, enriched with valuation and ownership."""

    parcel_id: str
    address: str
    city: str
    state: str
    zip_code: str
    lat: float
    lon: float
    year_built: int | None = None
    lot_size_sqft: float | None = None
    estimated_value: float | None = None
    owner_name: str | None = None
    assessor_url: str | None = None
    zillow_url: str | None = None
    provenance: Provenance


OwnershipType = Literal["individual", "trust", "corporate", "government", "unknown"]


class OwnershipClassification(BaseModel):
    owner_name: str
    ownership_type: OwnershipType
    confidence: float
    matched_rule: str
    needs_review: bool


class DeveloperMatch(BaseModel):
    """A developer whose buy-box fits a candidate parcel, with their max land offer."""

    developer: str
    fit: float
    max_offer: float
    rationale: str


class Candidate(BaseModel):
    parcel: Parcel
    ownership: OwnershipClassification
    nearest_anchor_id: str
    distance_to_anchor_ft: float
    value_gap: float
    score: float
    score_breakdown: dict[str, float]
    developer_matches: list[DeveloperMatch] = []


class Cluster(BaseModel):
    id: str
    anchor_ids: list[str]
    anchors: list[AnchorHome]
    centroid_lat: float
    centroid_lon: float
    bbox: tuple[float, float, float, float]
    avg_anchor_price: float
    is_singleton: bool
    candidates: list[Candidate]


class RunSummary(BaseModel):
    market: str
    generated_at: datetime
    config: dict
    anchors_found: int
    clusters_found: int
    parcels_scanned: int
    candidates_returned: int
    stale_sources: list[str]
    review_queue: list[OwnershipClassification]


class RunResult(BaseModel):
    summary: RunSummary
    clusters: list[Cluster]
