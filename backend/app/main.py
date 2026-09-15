from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.config import SearchConfig
from app.export import candidates_to_csv
from app.models import RunResult
from app.pipeline import run_pipeline
from app.providers import (
    MissingCredentialsError,
    available_markets,
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
    return available_markets()


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
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/run", response_model=RunResult)
def run(config: SearchConfig, listing_source: str = "fixture", parcel_source: str = "fixture") -> RunResult:
    return _run(config, listing_source, parcel_source)


@app.post("/api/run/export.csv", response_class=PlainTextResponse)
def run_export(
    config: SearchConfig, listing_source: str = "fixture", parcel_source: str = "fixture"
) -> PlainTextResponse:
    csv_text = candidates_to_csv(_run(config, listing_source, parcel_source))
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="ultraspec-{config.market}.csv"'},
    )
