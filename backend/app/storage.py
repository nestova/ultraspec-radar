"""Persists every pipeline run — config, summary and full results — to SQLite.

Runs are saved automatically by the API layer so no search is lost. The store
lives outside the repo in dev containers (`RUN_DB_PATH`), falling back to
`backend/data/runs.db` for bare-metal local runs.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.models import RunResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    market TEXT NOT NULL,
    listing_source TEXT NOT NULL,
    parcel_source TEXT NOT NULL,
    anchors_found INTEGER NOT NULL,
    clusters_found INTEGER NOT NULL,
    parcels_scanned INTEGER NOT NULL,
    candidates_returned INTEGER NOT NULL,
    result_json TEXT NOT NULL
)
"""


def _db_path() -> Path:
    return Path(os.getenv("RUN_DB_PATH", "data/runs.db"))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def save_run(result: RunResult, listing_source: str, parcel_source: str) -> str:
    run_id = uuid.uuid4().hex
    summary = result.summary
    with _connect() as connection:
        connection.execute(_SCHEMA)
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                datetime.now(timezone.utc).isoformat(),
                summary.market,
                listing_source,
                parcel_source,
                summary.anchors_found,
                summary.clusters_found,
                summary.parcels_scanned,
                summary.candidates_returned,
                result.model_dump_json(),
            ),
        )
    return run_id


def list_runs(limit: int = 50) -> list[dict]:
    with _connect() as connection:
        connection.execute(_SCHEMA)
        rows = connection.execute(
            "SELECT id, created_at, market, listing_source, parcel_source,"
            " anchors_found, clusters_found, parcels_scanned, candidates_returned"
            " FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: str) -> RunResult:
    with _connect() as connection:
        connection.execute(_SCHEMA)
        row = connection.execute(
            "SELECT result_json FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
    if row is None:
        raise KeyError(f"No saved run '{run_id}'.")
    return RunResult.model_validate_json(row["result_json"])
