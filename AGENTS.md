# UltraSpec Radar — Base44 Dev Environment

## Architecture

Fullstack app: FastAPI backend (Python) + React/Vite frontend (TypeScript).
- **Run store** — every pipeline run is auto-saved (full result + config) to SQLite (`app/storage.py`, env `RUN_DB_PATH`). In compose it lives in the named volume `run-data` at `/app/rundata/runs.db`, persisting across container recreation; local non-docker runs default to `backend/data/runs.db` (gitignored). `GET /api/runs` lists saved runs, `GET /api/runs/{id}` returns a full saved result. The frontend shows saved runs in the ControlRail and reloads them on click.
- **No other database** — the backend reads live Miami-Dade public data by default (see Data sources), with an offline JSON fixture as fallback.
- Single-origin wiring: only port 3000 is public (frontend Vite dev server). The frontend proxies `/api` to the backend at `http://backend:8000` via Vite's `server.proxy` config (`VITE_API_TARGET` env var).

## Running

```bash
docker compose -f docker-compose.base44.yml up -d --build
```

- `backend` — `python:3.12-slim`, installs `requirements.txt`, runs `uvicorn --reload` on port 8000 (internal only, not host-exposed).
- `frontend` — `node:22`, runs `npm install && npm run dev` on port 5173, mapped to host port 3000.

## Data sources

- **Default (live)**: `miamidade` providers (`backend/app/providers/miamidade.py`) query the Miami-Dade Property Appraiser's tax roll on the county GIS ArcGIS Hub ("Property Point View" layer). Public, no credentials. Anchors = single-family (DOR 0101) parcels with assessed value ≥ threshold and year built ≥ threshold; parcels = server-side radius queries in feet. First run of a config takes ~15-30s (one county query per anchor); results are cached in-process for 10 min. Network/API failures raise `ProviderUnavailableError` → HTTP 502.
- **Paradise Valley, AZ (live)**: `maricopa` providers (`backend/app/providers/maricopa.py`) query the Maricopa County Assessor's parcel MapServer (`gis.mcassessor.maricopa.gov`). Its FCV/year-built fields are comma-formatted STRINGS, so numeric server-side WHERE clauses fail — the provider bulk-fetches all ~7k "PARADISE VALLEY" residential (PUC 01xx) rows once, caches them 10 min, and filters anchors/radii in memory (`haversine_ft`). First scan ~15s, repeats instant.
- **County ArcGIS providers** (`backend/app/providers/county_sources.py` + `counties.py`): one generic provider pair serves every county that publishes a public ArcGIS parcel layer. Configs live in `COUNTY_SOURCES`; two modes:
  - *bulk* — fetch the whole market slice once (10-min in-process cache), filter anchors/radii in memory (Maricopa's pattern). Used by `collier` (Port Royal via Collier CityView parcels — 462 rows; year built is NOT on the county layer, so `FL_STATEWIDE_URL` enriches it via batched 50-folio `PARCEL_ID IN` lookups; larger IN batches and spatial/attribute scans on the statewide layer time out — keep batches small), `manatee` (Anna Maria Island cities), `nys` (NYS Tax Parcels, Suffolk towns of East Hampton & Southampton; note `COUNTY_NAME='Suffolk'` is case-sensitive).
  - *query* — server-side WHERE for anchors + envelope queries per anchor radius (cached). Used by `mecklenburg` (Charlotte Myers Park corridor bbox in `MECKLENBURG`'s `anchor_envelope`; `totmarkval`/`yearbuilt` filter server-side), `clark` (Clark County tax roll hosted by the City of Henderson's AGOL org; values are Nevada *taxable* values, ~1/3–½ of market, so anchor `min_price` thresholds must be scaled down per run).
- **Value semantics vary by market**: miamidade/collier/manatee/nys values are market-ish; mecklenburg ~ assessed market; maricopa is full cash value; clark is taxable. Anchor/candidate thresholds are per-run config in the ControlRail — tune per market.
- **Source routing**: `/api/run` takes `listing_source`/`parcel_source` (default `auto`), resolved per market via `MARKET_SOURCES` in `main.py` (miami-dade-fl→miamidade, paradise-valley-az→maricopa, port-royal-naples-fl→collier, bradenton-anna-maria-fl→manatee, hamptons-ny→nys, charlotte-nc→mecklenburg, las-vegas-henderson-nv→clark, bel-air-beverly-hills-ca→regrid, seattle-eastside-wa→regrid, atherton-ca→regrid). Explicit names (`fixture`, etc.) still work.
- **Regrid markets** (`backend/app/providers/regrid.py`): bel-air-beverly-hills-ca, seattle-eastside-wa (Medina/Hunts Point), atherton-ca — the markets whose public county feeds lack owner/year-built attributes. Uses the Regrid API v2 `/parcels/query` endpoint with `REGRID_API_TOKEN` (sandbox plan, **~2000 properties/month**). Frugality is built in: server-side filters (`fields[yearbuilt][gte]`, `fields[ll_gissqft][gte]`=5000 to drop condos), payload trimming, `offset_id` pagination capped at 4×1000, and the same 10-min in-process cache as the other providers (repeated scans within 10 min cost nothing). Missing/rejected token → `MissingCredentialsError` → HTTP 503. `parval` is NOT server-side queryable — value thresholds filter client-side on anchors only. **Value semantics**: CA `parval` is Prop-13 assessed (far below market unless recently sold) — tune `anchor_min_price`/`candidate_max_value` down heavily for Atherton/Bel Air; King County WA parval is assessed market-ish. **Sandbox token limitation**: API sandbox tokens only cover a fixed trial county set (the current one = Marion County, IN only — verified: path queries for san-mateo/los-angeles/king return 0 features). The three Regrid markets therefore return empty scans until a production/county-licensed token is set; the usage endpoint is `GET /api/v2/usage?token=...` (free). API v2 nests attributes under `properties.fields` (handled in `_row`).
- **Offline fallback**: `fixture` providers read `backend/data/miami-dade-fl.json`. Select via `POST /api/run?listing_source=fixture&parcel_source=fixture`.
- **Waterfront classification** (`backend/app/waterfront.py`): the tax rolls carry no waterfront flag, so parcels are classified geometrically against `backend/data/water.geojson` (Natural Earth 10m ocean + lakes, pre-clipped to the market regions, ~125 KB). A parcel is waterfront if it sits in water or within 250 ft of it (`WATERFRONT_MAX_FT`). Every scanned parcel gets `parcel.waterfront` (True/False; null when the file is missing) and the ControlRail has a "Waterfront only" candidate filter (`waterfront_only` in SearchConfig; the CSV export has a `waterfront` column). Coverage: oceans, open bays (Biscayne Bay, Shinnecock Bay, Naples/Gordon Pass) and major lakes (Mead, Okeechobee). Below dataset resolution (NOT flagged): residential canals, enclosed bays (SF Bay, Peconic Bay, Sarasota Bay), Lake Washington/Sammamish.
- The county layer's field names are prefixed `TRUE_` (e.g. `TRUE_SITE_ADDR`, `TRUE_OWNER1`) and single-family is DOR code `0101` (not `0100`).

## Secrets

- `ATTOM_API_KEY` — **optional**. Only needed for the licensed ATTOM production data feed. Without it, the app runs on the live Miami-Dade public data by default. The `attom` provider raises a clear 503 error until provisioned.
- `REGRID_API_TOKEN` — sandbox token from https://app.regrid.com/. Required for the Regrid-backed markets (Bel Air/Beverly Hills, Seattle Eastside, Atherton); without it those markets return 503. Metered ~2000 properties/month — don't run broad repeat scans of them.

## Verifying

- `curl http://localhost:3000/api/health` → `{"status":"ok"}`
- `curl http://localhost:3000/api/markets` → list of available markets
- `curl -X POST http://localhost:3000/api/run` → runs the full pipeline

## Notes

- Frontend uses `react-leaflet` for map rendering (ClusterMap component).
- Vite 7 — `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` is passed from the platform env to allow the preview's external hostname.
- Backend healthcheck polls `/api/health`; frontend `depends_on` backend being healthy before starting.
