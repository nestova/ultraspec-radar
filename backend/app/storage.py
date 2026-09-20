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

from app.models import ContactUpdate, RunResult, SavedProperty, SavedPropertyIn

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

_PROPERTIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    parcel_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    market TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    year_built INTEGER,
    lot_size_sqft REAL,
    estimated_value REAL,
    owner_name TEXT,
    waterfront INTEGER,
    contact_name TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    notes TEXT
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


def _property_from_row(row: sqlite3.Row) -> SavedProperty:
    data = dict(row)
    data["waterfront"] = bool(data["waterfront"]) if data["waterfront"] is not None else None
    return SavedProperty.model_validate(data)


def upsert_property(prop: SavedPropertyIn) -> SavedProperty:
    """Insert a saved property; re-saving the same parcel refreshes its facts
    but never touches contact details the user has entered."""
    now = datetime.now(timezone.utc).isoformat()
    parcel_id = prop.parcel_id or f"manual-{uuid.uuid4().hex[:12]}"
    with _connect() as connection:
        connection.execute(_PROPERTIES_SCHEMA)
        connection.execute(
            """INSERT INTO properties (
                   parcel_id, created_at, updated_at, market, address, city, state,
                   zip_code, lat, lon, year_built, lot_size_sqft, estimated_value,
                   owner_name, waterfront
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(parcel_id) DO UPDATE SET
                   updated_at = excluded.updated_at,
                   market = excluded.market,
                   address = excluded.address,
                   city = excluded.city,
                   state = excluded.state,
                   zip_code = excluded.zip_code,
                   lat = excluded.lat,
                   lon = excluded.lon,
                   year_built = excluded.year_built,
                   lot_size_sqft = excluded.lot_size_sqft,
                   estimated_value = excluded.estimated_value,
                   owner_name = excluded.owner_name,
                   waterfront = excluded.waterfront""",
            (
                parcel_id, now, now, prop.market, prop.address, prop.city,
                prop.state, prop.zip_code, prop.lat, prop.lon, prop.year_built,
                prop.lot_size_sqft, prop.estimated_value, prop.owner_name,
                prop.waterfront,
            ),
        )
        row = connection.execute(
            "SELECT * FROM properties WHERE parcel_id = ?", (parcel_id,)
        ).fetchone()
    return _property_from_row(row)


def list_properties() -> list[SavedProperty]:
    with _connect() as connection:
        connection.execute(_PROPERTIES_SCHEMA)
        rows = connection.execute(
            "SELECT * FROM properties ORDER BY created_at DESC"
        ).fetchall()
    return [_property_from_row(row) for row in rows]


def update_property_contacts(parcel_id: str, contact: ContactUpdate) -> SavedProperty:
    with _connect() as connection:
        connection.execute(_PROPERTIES_SCHEMA)
        row = connection.execute(
            "SELECT * FROM properties WHERE parcel_id = ?", (parcel_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No saved property '{parcel_id}'.")
        merged = {
            field: getattr(contact, field)
            if getattr(contact, field) is not None
            else row[field]
            for field in ("contact_name", "contact_phone", "contact_email", "notes")
        }
        connection.execute(
            "UPDATE properties SET contact_name = ?, contact_phone = ?,"
            " contact_email = ?, notes = ?, updated_at = ? WHERE parcel_id = ?",
            (
                merged["contact_name"], merged["contact_phone"],
                merged["contact_email"], merged["notes"],
                datetime.now(timezone.utc).isoformat(), parcel_id,
            ),
        )
        row = connection.execute(
            "SELECT * FROM properties WHERE parcel_id = ?", (parcel_id,)
        ).fetchone()
    return _property_from_row(row)


def delete_property(parcel_id: str) -> None:
    with _connect() as connection:
        connection.execute(_PROPERTIES_SCHEMA)
        cursor = connection.execute(
            "DELETE FROM properties WHERE parcel_id = ?", (parcel_id,)
        )
    if cursor.rowcount == 0:
        raise KeyError(f"No saved property '{parcel_id}'.")


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
