# UltraSpec Radar — Base44 Dev Environment

## Architecture

Fullstack app: FastAPI backend (Python) + React/Vite frontend (TypeScript).
- **No database** — the backend reads live Miami-Dade public data by default (see Data sources), with an offline JSON fixture as fallback.
- Single-origin wiring: only port 3000 is public (frontend Vite dev server). The frontend proxies `/api` to the backend at `http://backend:8000` via Vite's `server.proxy` config (`VITE_API_TARGET` env var).

## Running

```bash
docker compose -f docker-compose.base44.yml up -d --build
```

- `backend` — `python:3.12-slim`, installs `requirements.txt`, runs `uvicorn --reload` on port 8000 (internal only, not host-exposed).
- `frontend` — `node:22`, runs `npm install && npm run dev` on port 5173, mapped to host port 3000.

## Data sources

- **Default (live)**: `miamidade` providers (`backend/app/providers/miamidade.py`) query the Miami-Dade Property Appraiser's tax roll on the county GIS ArcGIS Hub ("Property Point View" layer). Public, no credentials. Anchors = single-family (DOR 0101) parcels with assessed value ≥ threshold and year built ≥ threshold; parcels = server-side radius queries in feet. First run of a config takes ~15-30s (one county query per anchor); results are cached in-process for 10 min. Network/API failures raise `ProviderUnavailableError` → HTTP 502.
- **Offline fallback**: `fixture` providers read `backend/data/miami-dade-fl.json`. Select via `POST /api/run?listing_source=fixture&parcel_source=fixture`.
- The county layer's field names are prefixed `TRUE_` (e.g. `TRUE_SITE_ADDR`, `TRUE_OWNER1`) and single-family is DOR code `0101` (not `0100`).

## Secrets

- `ATTOM_API_KEY` — **optional**. Only needed for the licensed ATTOM production data feed. Without it, the app runs on the live Miami-Dade public data by default. The `attom` provider raises a clear 503 error until provisioned.

## Verifying

- `curl http://localhost:3000/api/health` → `{"status":"ok"}`
- `curl http://localhost:3000/api/markets` → list of available markets
- `curl -X POST http://localhost:3000/api/run` → runs the full pipeline

## Notes

- Frontend uses `react-leaflet` for map rendering (ClusterMap component).
- Vite 7 — `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` is passed from the platform env to allow the preview's external hostname.
- Backend healthcheck polls `/api/health`; frontend `depends_on` backend being healthy before starting.
