"""Generate the offline pilot-market dataset used by the fixture providers.

The records are synthetic but structurally identical to what a licensed feed
(ATTOM/Bridge) plus a county assessor GIS layer returns, so the pipeline can be
exercised end-to-end without scraping Zillow.

Usage: python scripts/generate_fixture.py
"""

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "miami-dade-fl.json"
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
FT_PER_DEG_LAT = 364_000.0

NEIGHBORHOODS = [
    ("Miami Beach", "33139", 25.7907, -80.1400, "North Bay Road"),
    ("Coconut Grove", "33133", 25.7276, -80.2430, "Leafy Way"),
    ("Bal Harbour", "33154", 25.8917, -80.1230, "Bal Bay Drive"),
    ("Key Biscayne", "33149", 25.6906, -80.1620, "Harbor Drive"),
]

BUILDERS = ["Todd Michael Glaser", "Adam Ostrower Dev", "SDH Studio Build", "Cassis Group"]

FIRST = ["Robert", "Maria", "James", "Linda", "Carlos", "Susan", "Daniel", "Patricia", "Henry", "Elena"]
LAST = ["Alvarez", "Whitfield", "Moreno", "Castellano", "Ferguson", "Delgado", "Kaplan", "Brennan"]
CORPORATE = [
    "Bay Road Holdings LLC",
    "Sunset Isles Properties Inc",
    "Grove Capital Partners LP",
    "Atlantic Realty Group LLC",
]


def offset(lat: float, lon: float, north_ft: float, east_ft: float) -> tuple[float, float]:
    ft_per_deg_lon = FT_PER_DEG_LAT * math.cos(math.radians(lat))
    return lat + north_ft / FT_PER_DEG_LAT, lon + east_ft / ft_per_deg_lon


def provenance(source: str, url: str, days_old: int) -> dict:
    return {
        "source": source,
        "source_url": url,
        "retrieved_at": (NOW - timedelta(days=days_old)).isoformat(),
    }


def main() -> None:
    rng = random.Random(20260915)
    anchors: list[dict] = []
    parcels: list[dict] = []

    for n_index, (city, zip_code, base_lat, base_lon, street) in enumerate(NEIGHBORHOODS):
        # Bal Harbour gets a single anchor so singleton handling is exercised.
        anchor_count = 1 if city == "Bal Harbour" else rng.choice([2, 3])
        anchor_points = []

        for a_index in range(anchor_count):
            lat, lon = offset(base_lat, base_lon, a_index * 900, a_index * 700)
            number = 1200 + n_index * 100 + a_index * 8
            anchor_id = f"anchor-{n_index + 1}-{a_index + 1}"
            anchors.append(
                {
                    "id": anchor_id,
                    "address": f"{number} {street}",
                    "city": city,
                    "state": "FL",
                    "zip_code": zip_code,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "price": float(rng.choice([15_750_000, 18_500_000, 22_000_000, 27_400_000, 34_900_000])),
                    "status": rng.choice(["listed", "under_contract", "sold"]),
                    "year_built": rng.choice([2023, 2024, 2025]),
                    "builder": rng.choice(BUILDERS),
                    "parcel_id": f"02-32{n_index}{a_index}-001-0010",
                    "listing_url": f"https://www.example-mls.com/listing/{anchor_id}",
                    "provenance": provenance(
                        "miami-dade-permits+mls-feed",
                        "https://www.miamidade.gov/permits",
                        rng.randint(2, 20),
                    ),
                }
            )
            anchor_points.append((lat, lon))

        # Neighbors: a mix that passes and fails each filter stage.
        for p_index in range(10):
            a_lat, a_lon = anchor_points[p_index % len(anchor_points)]
            bearing = rng.uniform(0, 2 * math.pi)
            radius_ft = rng.uniform(80, 900)
            lat, lon = offset(a_lat, a_lon, radius_ft * math.cos(bearing), radius_ft * math.sin(bearing))

            if p_index % 5 == 0:
                owner = rng.choice(CORPORATE)
            elif p_index % 5 == 1:
                owner = f"{rng.choice(LAST)} Family Trust"
            elif p_index % 5 == 2:
                owner = f"{rng.choice(FIRST)} {rng.choice(LAST)} Revocable Trust"
            elif p_index % 5 == 3:
                owner = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            else:
                owner = f"{rng.choice(FIRST)} {rng.choice(LAST)} & {rng.choice(FIRST)} {rng.choice(LAST)}"

            year_built = rng.choice([1938, 1947, 1955, 1962, 1968, 1970, 1984, 1999, 2012])
            value = float(rng.choice([1_150_000, 1_640_000, 1_950_000, 2_300_000, 2_480_000, 3_900_000]))
            parcel_id = f"02-32{n_index}{p_index}-002-{1000 + p_index}"
            parcels.append(
                {
                    "parcel_id": parcel_id,
                    "address": f"{1300 + n_index * 100 + p_index * 6} {street}",
                    "city": city,
                    "state": "FL",
                    "zip_code": zip_code,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "year_built": year_built,
                    "lot_size_sqft": float(rng.choice([6_500, 8_200, 9_800, 12_400, 15_600, 21_000])),
                    "estimated_value": value,
                    "owner_name": owner,
                    "assessor_url": f"https://www.miamidade.gov/Apps/PA/propertysearch/#/?folio={parcel_id}",
                    "zillow_url": f"https://www.zillow.com/homes/{parcel_id}_rb/",
                    "provenance": provenance(
                        "miami-dade-property-appraiser+avm",
                        "https://www.miamidade.gov/pa/property_search.asp",
                        rng.randint(1, 25),
                    ),
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "label": "Miami-Dade County, FL (pilot)",
                "generated_at": NOW.isoformat(),
                "note": "Synthetic pilot dataset. Replace with a licensed feed before production use.",
                "anchors": anchors,
                "parcels": parcels,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {OUT} ({len(anchors)} anchors, {len(parcels)} parcels)")


if __name__ == "__main__":
    main()
