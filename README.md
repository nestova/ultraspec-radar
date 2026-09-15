# UltraSpec Radar

Finds geographic clusters of new-construction, ultra-luxury homes ($15M+) and surfaces nearby older,
individually-owned parcels with low relative value — teardown, assemblage, and value-gap targets.

Implements the MVP scope of `PRD — UltraSpec Radar`: single pilot market, batch run, cluster detection →
500 ft parcel search → value/age filter → ownership filter → ranked output with CSV export.

## Pipeline

| Step | Module | Notes |
|---|---|---|
| 1. Discover $15M+ new construction | `app/providers` | Pluggable; ships with an offline pilot dataset |
| 2. Cluster detection | `app/clustering.py` | DBSCAN on haversine distance, default 0.5 mi / ≥2 anchors |
| 3. Adjacent parcel search | `app/pipeline.py` | 500 ft radius per anchor, deduped to the nearest anchor |
| 4. Value & age filter | `app/pipeline.py` | ≤$2.5M estimated value, built 1970 or earlier |
| 5. Ownership filter | `app/ownership.py` | Excludes LLC/corporate; trusts count as individual |
| 6. Rank & output | `app/pipeline.py`, `app/export.py` | Weighted proximity / value gap / lot size, ≤10 per cluster |

Every threshold in the table is a request parameter (`app/config.py`), not a constant. Each record keeps its
source and retrieval timestamp, and the run summary flags sources older than the freshness limit.

## Data sources

The PRD rules out scraping Zillow, and no licensed feed credentials are wired up yet, so the default
providers read **Miami-Dade County public data**: the Property Appraiser's certified tax roll published on
the county GIS open data hub (ArcGIS Hub "Property Point View" layer, DOR use code 0101 / single family).
`app/providers/miamidade.py` identifies anchors by assessed value + year built and fetches neighboring
parcels with a server-side radius query — no credentials needed, with a short-lived cache to spare the
county endpoint. `POST /api/run?listing_source=fixture&parcel_source=fixture` switches to the offline
synthetic pilot dataset (`backend/data/miami-dade-fl.json`, regenerate with
`python scripts/generate_fixture.py`), which stays structurally identical to a licensed feed.

`app/providers/attom.py` is the placeholder for the licensed production path; it raises a clear error until
`ATTOM_API_KEY` is provisioned. Add new sources by implementing `ListingProvider` / `ParcelProvider` and
registering them in `app/providers/__init__.py`.

## Running locally

Backend (Python 3.10+):

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20.19+):

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to port 8000
```

## Checks

```bash
cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check app tests scripts
cd frontend && npm run lint && npm run build
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/markets` | Markets with a loaded dataset |
| GET | `/api/config/defaults` | Default thresholds and ranking weights |
| POST | `/api/run` | Run the pipeline, returns clusters + candidates + run summary |
| POST | `/api/run/export.csv` | Same run, as a spreadsheet export |

## Out of scope

Owner outreach (explicitly excluded by the PRD), multi-market expansion, saved searches and new-cluster
alerts, and Secretary-of-State entity-registry cross-checks — the ownership classifier is name-pattern based
and routes ambiguous names to a review queue exposed in the run summary.
