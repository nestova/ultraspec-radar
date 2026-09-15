# UltraSpec Radar — Base44 Dev Environment

## Architecture

Fullstack app: FastAPI backend (Python) + React/Vite frontend (TypeScript).
- **No database** — the backend reads an offline synthetic JSON dataset (`backend/data/miami-dade-fl.json`).
- Single-origin wiring: only port 3000 is public (frontend Vite dev server). The frontend proxies `/api` to the backend at `http://backend:8000` via Vite's `server.proxy` config (`VITE_API_TARGET` env var).

## Running

```bash
docker compose -f docker-compose.base44.yml up -d --build
```

- `backend` — `python:3.12-slim`, installs `requirements.txt`, runs `uvicorn --reload` on port 8000 (internal only, not host-exposed).
- `frontend` — `node:22`, runs `npm install && npm run dev` on port 5173, mapped to host port 3000.

## Secrets

- `ATTOM_API_KEY` — **optional**. Only needed for the licensed ATTOM production data feed. Without it, the app runs on the built-in offline pilot dataset. The `attom` provider raises a clear 503 error until provisioned.

## Verifying

- `curl http://localhost:3000/api/health` → `{"status":"ok"}`
- `curl http://localhost:3000/api/markets` → list of available markets
- `curl -X POST http://localhost:3000/api/run` → runs the full pipeline

## Notes

- Frontend uses `react-leaflet` for map rendering (ClusterMap component).
- Vite 7 — `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` is passed from the platform env to allow the preview's external hostname.
- Backend healthcheck polls `/api/health`; frontend `depends_on` backend being healthy before starting.
