from pydantic import BaseModel, Field


class SearchConfig(BaseModel):
    """Tunable pipeline parameters. Nothing here is hardcoded in the pipeline."""

    market: str = "miami-dade-fl"

    anchor_min_price: float = Field(15_000_000, gt=0)
    anchor_min_year_built: int = 2023

    cluster_radius_miles: float = Field(0.5, gt=0)
    cluster_min_members: int = Field(2, ge=1)
    allow_singleton_clusters: bool = False

    adjacent_radius_feet: float = Field(500, gt=0)

    candidate_max_value: float = Field(2_500_000, gt=0)
    candidate_max_year_built: int = 1970

    exclude_corporate_owners: bool = True
    include_trusts: bool = True
    waterfront_only: bool = False

    weight_proximity: float = 0.5
    weight_value_gap: float = 0.3
    weight_lot_size: float = 0.2

    max_candidates_per_cluster: int = Field(10, ge=1)
    max_data_age_days: int = Field(30, ge=1)
