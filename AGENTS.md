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

## Credentials
- `TRACERFY_API_KEY` (optional) — Tracerfy MCP connector token. Generate it in your Tracerfy
  profile → Connect via MCP; the value can be the full connector URL or just the token. Wired into
  the backend via `env_file: /run/base44/app.env`. Each pipeline run costs Tracerfy credits (5 per
  row): 50 anchors + 50 parcels = 500 credits.
- The default `fixture` provider needs no credentials and reads an offline synthetic dataset
  (`backend/data/miami-dade-fl.json`).

## Tracerfy MCP provider (skip trace only)
`app/providers/tracerfy.py` implements `SkipTraceProvider` — it calls the Tracerfy MCP server's
`trace_lookup` tool to retrieve owner phone numbers and email addresses for a property address.
It does NOT fetch property data; the fixture provider supplies anchors and parcels. The MCP
client (`app/providers/mcp_client.py`) is built on httpx — the official `mcp` package conflicts
with FastAPI's starlette pin. Call it via `POST /api/skip-trace` with `{address, city, state,
zip_code}`. Tracerfy bills credits per hit; a miss costs nothing.

## Key conventions
- Every pipeline threshold is a request parameter (`app/config.py`), never a constant.
- New data sources implement `ListingProvider` / `ParcelProvider` and register in `app/providers/__init__.py`.
- Frontend calls the API via relative `/api/*` paths only (relies on the Vite proxy).

## Checks
```bash
docker compose -f docker-compose.base44.yml exec -T backend python -m pytest -q
docker compose -f docker-compose.base44.yml exec -T frontend sh -c "npm run lint && npm run build"
```
