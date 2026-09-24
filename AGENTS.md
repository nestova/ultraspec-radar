# UltraSpec Radar — Base44 dev environment

## Architecture
Single-origin dev setup: Vite frontend (host port 3000 → container 5173) proxies `/api/*` to the
FastAPI backend (container port 8000, not exposed publicly). Both services bind-mount the cloned
source and run live-reload dev commands, so edits appear without image rebuilds.

## Running
```bash
docker compose -f docker-compose.base44.yml up -d --build
```
Frontend health: `http://localhost:3000/` · Backend health: `http://localhost:8000/api/health`

## Data providers

### Miami-Dade Property Appraiser (default — no API key needed)
`app/providers/miami_dade.py` implements both `ListingProvider` and `ParcelProvider` by querying
the county's public ArcGIS REST Feature Service (Property Point View, 943K+ records, updated
weekly). Anchors: single-family homes (DOR code `01%`) filtered by assessed value and year built.
Parcels: envelope query around each anchor, filtered by haversine distance. No authentication
required. This is the default source (`listing_source=miami-dade&parcel_source=miami-dade`).

### Fixture (offline fallback)
The `fixture` provider reads a synthetic dataset (`backend/data/miami-dade-fl.json`) and needs no
credentials or network. Use it by passing `listing_source=fixture&parcel_source=fixture`.

## Tracerfy MCP provider (skip trace only)
`app/providers/tracerfy.py` implements `SkipTraceProvider` — it calls the Tracerfy MCP server's
`trace_lookup` tool to retrieve owner phone numbers and email addresses for a property address.
It does NOT fetch property data; the Miami-Dade provider supplies anchors and parcels. The MCP
client (`app/providers/mcp_client.py`) is built on httpx — the official `mcp` package conflicts
with FastAPI's starlette pin. Call it via `POST /api/skip-trace` with `{address, city, state,
zip_code}`. Tracerfy bills credits per hit; a miss costs nothing.

## Credentials
- `TRACERFY_API_KEY` (optional) — Tracerfy MCP connector token for skip tracing. Generate it in
  your Tracerfy profile → Connect via MCP; the value can be the full connector URL or just the
  token. Wired into the backend via `env_file: /run/base44/app.env`.

## Key conventions
- Every pipeline threshold is a request parameter (`app/config.py`), never a constant.
- New data sources implement `ListingProvider` / `ParcelProvider` and register in `app/providers/__init__.py`.
- Frontend calls the API via relative `/api/*` paths only (relies on the Vite proxy).

## Checks
```bash
docker compose -f docker-compose.base44.yml exec -T backend python -m pytest -q
docker compose -f docker-compose.base44.yml exec -T frontend sh -c "npm run lint && npm run build"
```
