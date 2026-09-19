from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app import storage
from app.config import SearchConfig
from app.developers import developer_names
from app.export import candidates_to_csv
from app.markets import MARKETS
from app.models import RunResult
from app.pipeline import run_pipeline
from app.providers import (
    MissingCredentialsError,
    ProviderUnavailableError,
    get_listing_provider,
    get_parcel_provider,
)

app = FastAPI(title="UltraSpec Radar", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/markets")
def markets() -> list[dict]:
    return [
        {
            "id": market_id,
            "label": label,
            "scannable": scannable,
            "developers": developer_names(market_id),
        }
        for market_id, label, scannable in MARKETS
    ]


# Live data source per market; "auto" (the default) resolves via this map.
MARKET_SOURCES = {
    "miami-dade-fl": "miamidade",
    "paradise-valley-az": "maricopa",
    "port-royal-naples-fl": "collier",
    "bradenton-anna-maria-fl": "manatee",
    "hamptons-ny": "nys",
    "charlotte-nc": "mecklenburg",
    "las-vegas-henderson-nv": "clark",
}


def _resolve_sources(config: SearchConfig, listing_source: str, parcel_source: str) -> tuple[str, str]:
    if listing_source == "auto":
        listing_source = MARKET_SOURCES.get(config.market, "")
        if not listing_source:
            raise ValueError(f"No live data source connected for market '{config.market}'.")
    if parcel_source == "auto":
        parcel_source = MARKET_SOURCES.get(config.market, "")
        if not parcel_source:
            raise ValueError(f"No live data source connected for market '{config.market}'.")
    return listing_source, parcel_source


@app.get("/api/config/defaults", response_model=SearchConfig)
def config_defaults() -> SearchConfig:
    return SearchConfig()


def _run(config: SearchConfig, listing_source: str, parcel_source: str) -> RunResult:
    try:
        return run_pipeline(
            config,
            get_listing_provider(listing_source),
            get_parcel_provider(parcel_source),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissingCredentialsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/run", response_model=RunResult)
def run(
    config: SearchConfig, listing_source: str = "auto", parcel_source: str = "auto"
) -> RunResult:
    resolved = _resolve_sources(config, listing_source, parcel_source)
    result = _run(config, *resolved)
    storage.save_run(result, *resolved)
    return result


@app.post("/api/run/export.csv", response_class=PlainTextResponse)
def run_export(
    config: SearchConfig, listing_source: str = "auto", parcel_source: str = "auto"
) -> PlainTextResponse:
    resolved = _resolve_sources(config, listing_source, parcel_source)
    result = _run(config, *resolved)
    storage.save_run(result, *resolved)
    csv_text = candidates_to_csv(result)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="ultraspec-{config.market}.csv"'},
    )


@app.get("/api/runs")
def saved_runs(limit: int = 50) -> list[dict]:
    return storage.list_runs(limit)


@app.get("/api/runs/{run_id}", response_model=RunResult)
def saved_run(run_id: str) -> RunResult:
    try:
        return storage.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
