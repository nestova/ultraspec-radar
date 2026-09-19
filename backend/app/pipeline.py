from datetime import datetime, timedelta, timezone

from app.clustering import bbox, centroid, cluster_anchors
from app.config import SearchConfig
from app.developers import match_developers
from app.geo import haversine_ft
from app.models import (
    AnchorHome,
    Candidate,
    Cluster,
    OwnershipClassification,
    Parcel,
    RunResult,
    RunSummary,
)
from app.ownership import classify_owner, is_eligible
from app.providers.base import ListingProvider, ParcelProvider


def _normalize(values: list[float], higher_is_better: bool) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    scaled = [(v - lo) / (hi - lo) for v in values]
    return scaled if higher_is_better else [1.0 - s for s in scaled]


def _is_stale(retrieved_at: datetime, max_age_days: int) -> bool:
    now = datetime.now(timezone.utc)
    stamp = retrieved_at if retrieved_at.tzinfo else retrieved_at.replace(tzinfo=timezone.utc)
    return now - stamp > timedelta(days=max_age_days)


def _score_candidates(
    parcels: list[tuple[Parcel, OwnershipClassification, AnchorHome, float]],
    avg_anchor_price: float,
    config: SearchConfig,
) -> list[Candidate]:
    distances = [d for _, _, _, d in parcels]
    gaps = [max(avg_anchor_price - (p.estimated_value or 0.0), 0.0) for p, _, _, _ in parcels]
    lots = [p.lot_size_sqft or 0.0 for p, _, _, _ in parcels]

    proximity_scores = _normalize(distances, higher_is_better=False)
    gap_scores = _normalize(gaps, higher_is_better=True)
    lot_scores = _normalize(lots, higher_is_better=True)

    total_weight = config.weight_proximity + config.weight_value_gap + config.weight_lot_size
    total_weight = total_weight or 1.0

    candidates: list[Candidate] = []
    for i, (parcel, ownership, anchor, distance) in enumerate(parcels):
        breakdown = {
            "proximity": proximity_scores[i] * config.weight_proximity,
            "value_gap": gap_scores[i] * config.weight_value_gap,
            "lot_size": lot_scores[i] * config.weight_lot_size,
        }
        candidates.append(
            Candidate(
                parcel=parcel,
                ownership=ownership,
                nearest_anchor_id=anchor.id,
                distance_to_anchor_ft=round(distance, 1),
                value_gap=round(gaps[i], 2),
                score=round(sum(breakdown.values()) / total_weight, 4),
                score_breakdown={k: round(v, 4) for k, v in breakdown.items()},
            )
        )
    candidates.sort(key=lambda c: (-c.score, c.distance_to_anchor_ft))
    return candidates[: config.max_candidates_per_cluster]


def run_pipeline(
    config: SearchConfig,
    listing_provider: ListingProvider,
    parcel_provider: ParcelProvider,
) -> RunResult:
    anchors = listing_provider.fetch_anchors(
        config.market, config.anchor_min_price, config.anchor_min_year_built
    )

    stale_sources: set[str] = set()
    for anchor in anchors:
        if _is_stale(anchor.provenance.retrieved_at, config.max_data_age_days):
            stale_sources.add(anchor.provenance.source)

    anchor_groups = cluster_anchors(
        anchors,
        config.cluster_radius_miles,
        config.cluster_min_members,
        config.allow_singleton_clusters,
    )

    clusters: list[Cluster] = []
    review_queue: list[OwnershipClassification] = []
    parcels_scanned = 0

    for index, members in enumerate(anchor_groups, start=1):
        avg_price = sum(a.price for a in members) / len(members)
        anchor_ids = {a.id for a in members}

        # nearest-anchor dedupe across every anchor in the cluster
        nearest: dict[str, tuple[Parcel, AnchorHome, float]] = {}
        for anchor in members:
            for parcel in parcel_provider.fetch_parcels_near(
                config.market, anchor.lat, anchor.lon, config.adjacent_radius_feet
            ):
                if parcel.parcel_id in {a.parcel_id for a in members if a.parcel_id}:
                    continue
                distance = haversine_ft(anchor.lat, anchor.lon, parcel.lat, parcel.lon)
                existing = nearest.get(parcel.parcel_id)
                if existing is None or distance < existing[2]:
                    nearest[parcel.parcel_id] = (parcel, anchor, distance)

        parcels_scanned += len(nearest)

        filtered: list[tuple[Parcel, OwnershipClassification, AnchorHome, float]] = []
        for parcel, anchor, distance in nearest.values():
            if parcel.estimated_value is None or parcel.estimated_value > config.candidate_max_value:
                continue
            if parcel.year_built is None or parcel.year_built > config.candidate_max_year_built:
                continue
            if _is_stale(parcel.provenance.retrieved_at, config.max_data_age_days):
                stale_sources.add(parcel.provenance.source)

            ownership = classify_owner(parcel.owner_name)
            if ownership.needs_review:
                review_queue.append(ownership)
            if not is_eligible(ownership, config.include_trusts, config.exclude_corporate_owners):
                continue
            filtered.append((parcel, ownership, anchor, distance))

        candidates = _score_candidates(filtered, avg_price, config)
        for candidate in candidates:
            candidate.developer_matches = match_developers(candidate.parcel, avg_price, config.market)
        centroid_lat, centroid_lon = centroid(members)
        clusters.append(
            Cluster(
                id=f"cluster-{index}",
                anchor_ids=sorted(anchor_ids),
                anchors=members,
                centroid_lat=centroid_lat,
                centroid_lon=centroid_lon,
                bbox=bbox(members),
                avg_anchor_price=avg_price,
                is_singleton=len(members) == 1,
                candidates=candidates,
            )
        )

    summary = RunSummary(
        market=config.market,
        generated_at=datetime.now(timezone.utc),
        config=config.model_dump(),
        anchors_found=len(anchors),
        clusters_found=len(clusters),
        parcels_scanned=parcels_scanned,
        candidates_returned=sum(len(c.candidates) for c in clusters),
        stale_sources=sorted(stale_sources),
        review_queue=review_queue,
    )
    return RunResult(summary=summary, clusters=clusters)
