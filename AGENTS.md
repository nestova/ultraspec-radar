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
None required to boot. The default data provider (`fixture`) reads an offline synthetic dataset
(`backend/data/miami-dade-fl.json`). `ATTOM_API_KEY` is only for the licensed production path, which
is a placeholder that raises `NotImplementedError` — do not generate a placeholder for it.

## Key conventions
- Every pipeline threshold is a request parameter (`app/config.py`), never a constant.
- New data sources implement `ListingProvider` / `ParcelProvider` and register in `app/providers/__init__.py`.
- Frontend calls the API via relative `/api/*` paths only (relies on the Vite proxy).

## Checks
```bash
docker compose -f docker-compose.base44.yml exec -T backend python -m pytest -q
docker compose -f docker-compose.base44.yml exec -T frontend sh -c "npm run lint && npm run build"
```
