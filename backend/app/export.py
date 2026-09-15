import csv
import io

from app.models import RunResult

COLUMNS = [
    "cluster_id",
    "address",
    "city",
    "state",
    "zip_code",
    "parcel_id",
    "owner_name",
    "ownership_type",
    "needs_review",
    "year_built",
    "lot_size_sqft",
    "estimated_value",
    "distance_to_anchor_ft",
    "nearest_anchor_id",
    "nearest_anchor_address",
    "cluster_avg_anchor_price",
    "value_gap",
    "score",
    "assessor_url",
    "zillow_url",
    "source",
    "retrieved_at",
]


def candidates_to_csv(result: RunResult) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS)
    writer.writeheader()
    for cluster in result.clusters:
        anchors = {a.id: a for a in cluster.anchors}
        for candidate in cluster.candidates:
            parcel = candidate.parcel
            writer.writerow(
                {
                    "cluster_id": cluster.id,
                    "address": parcel.address,
                    "city": parcel.city,
                    "state": parcel.state,
                    "zip_code": parcel.zip_code,
                    "parcel_id": parcel.parcel_id,
                    "owner_name": parcel.owner_name,
                    "ownership_type": candidate.ownership.ownership_type,
                    "needs_review": candidate.ownership.needs_review,
                    "year_built": parcel.year_built,
                    "lot_size_sqft": parcel.lot_size_sqft,
                    "estimated_value": parcel.estimated_value,
                    "distance_to_anchor_ft": candidate.distance_to_anchor_ft,
                    "nearest_anchor_id": candidate.nearest_anchor_id,
                    "nearest_anchor_address": anchors[candidate.nearest_anchor_id].address,
                    "cluster_avg_anchor_price": round(cluster.avg_anchor_price, 2),
                    "value_gap": candidate.value_gap,
                    "score": candidate.score,
                    "assessor_url": parcel.assessor_url,
                    "zillow_url": parcel.zillow_url,
                    "source": parcel.provenance.source,
                    "retrieved_at": parcel.provenance.retrieved_at.isoformat(),
                }
            )
    return buffer.getvalue()
