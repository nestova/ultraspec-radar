"""Per-market county data-source configurations.

Each entry pins a live public county (or state) ArcGIS parcel layer, the
WHERE clause that scopes it to the market, and a row builder that
normalizes a raw feature into the app's typed row dict:

    {parcel_id, address, city, zip_code, lat, lon, year_built,
     value, lot_size_sqft, owner_name}

Two scopes are supported:
* `bulk_where` — the provider fetches the whole market slice once, caches
  it and filters anchors/radii in memory (Maricopa's pattern).
* `anchor_where` (+ optional `anchor_envelope`) — the provider issues
  server-side filtered anchor queries and envelope-based radius queries.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.providers.arcgis_rest import query_arcgis, to_float, to_int

Row = dict[str, Any]
RowBuilder = Callable[[dict], Row | None]

# Collier County parcels lack a year-built attribute; Florida's statewide
# cadastral (FL DOR roll) carries ACT_YR_BLT per folio and answers exact
# folio lookups quickly. Large spatial/attribute scans on it time out
# (see dead ends) — so we only do batched IN-lookups of 50 folios.
FL_STATEWIDE_URL = (
    "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/"
    "Florida_Statewide_Cadastral/FeatureServer/0/query"
)
_STATEWIDE_BATCH = 50
_folio_year: dict[str, tuple[float, int | None]] = {}  # folio -> (expires, year)
_FOLIO_TTL_SECONDS = 600


def _row(
    *,
    parcel_id: str | None,
    address: str,
    city: str,
    zip_code: str,
    lat: float | None,
    lon: float | None,
    year_built: int | None,
    value: float | None,
    lot_size_sqft: float | None,
    owner_name: str | None,
) -> Row | None:
    if not parcel_id or lat is None or lon is None:
        return None
    return {
        "parcel_id": str(parcel_id).strip(),
        "address": (address or "").strip(),
        "city": (city or "").strip(),
        "zip_code": str(zip_code or "").strip(),
        "lat": lat,
        "lon": lon,
        "year_built": year_built if year_built and year_built > 1700 else None,
        "value": value,
        "lot_size_sqft": lot_size_sqft,
        "owner_name": owner_name,
    }


def _centroid(feature: dict) -> tuple[float | None, float | None]:
    centroid = feature.get("centroid") or {}
    return to_float(centroid.get("y")), to_float(centroid.get("x"))


def _manatee_row(feature: dict) -> Row | None:
    a = feature.get("attributes", {})
    return _row(
        parcel_id=str(a.get("PARCEL_ID") or ""),
        address=a.get("PRIMARY_ADDRESS"),
        city=(a.get("PROP_CITYNAME") or "").title(),
        zip_code=a.get("PROP_ZIP"),
        lat=to_float(a.get("LAT")),
        lon=to_float(a.get("LON")),
        year_built=to_int(a.get("YRBLT_RES")),
        value=to_float(a.get("JUSTVAL")),
        lot_size_sqft=(
            (to_float(a.get("ACRES")) or 0.0) * 43_560 or None if to_float(a.get("ACRES")) else None
        ),
        owner_name=(str(a.get("OWNER")).strip() if a.get("OWNER") else None),
    )


def _nys_row(feature: dict) -> Row | None:
    a = feature.get("attributes", {})
    lat, lon = _centroid(feature)
    value = to_float(a.get("TOTAL_AV")) or to_float(a.get("FULL_MARKET_VAL"))
    acres = to_float(a.get("ACRES"))
    return _row(
        parcel_id=a.get("PRINT_KEY"),
        address=a.get("PARCEL_ADDR"),
        city=(a.get("CITYTOWN_NAME") or "").title(),
        zip_code=a.get("LOC_ZIP"),
        lat=lat,
        lon=lon,
        year_built=to_int(a.get("YR_BLT")),
        value=value,
        lot_size_sqft=to_float(a.get("SQ_FT")) or (acres * 43_560 if acres else None),
        owner_name=(str(a.get("PRIMARY_OWNER")).strip() if a.get("PRIMARY_OWNER") else None),
    )


def _collier_row(feature: dict) -> Row | None:
    a = feature.get("attributes", {})
    if str(a.get("USECODE") or "").strip() not in ("1", "01"):
        return None  # keep single-family residential rows only
    lat, lon = _centroid(feature)
    acres = to_float(a.get("TOTALACRES"))
    return _row(
        parcel_id=a.get("FOLIO"),
        address=a.get("FULLADDRESS"),
        city="Naples",
        zip_code="",
        lat=lat,
        lon=lon,
        year_built=None,  # enriched from the statewide cadastral below
        value=to_float(a.get("TOTALJUSTAMOUNT")),
        lot_size_sqft=acres * 43_560 if acres else None,
        owner_name=(str(a.get("NAME1")).strip() if a.get("NAME1") else None),
    )


def _collier_enrich_years(rows: list[Row], transport: Any = None) -> None:
    """Fill year_built on Collier rows via batched statewide folio lookups."""
    now = time.monotonic()
    unknown: list[str] = []
    for row in rows:
        folio = row["parcel_id"]
        cached = _folio_year.get(folio)
        if cached is None or cached[0] <= now:
            unknown.append(folio)
        else:
            row["year_built"] = cached[1] if row["year_built"] is None else row["year_built"]
    for start in range(0, len(unknown), _STATEWIDE_BATCH):
        batch = unknown[start : start + _STATEWIDE_BATCH]
        quoted = ",".join(f"'{folio}'" for folio in batch)
        features = query_arcgis(
            FL_STATEWIDE_URL,
            {"where": f"PARCEL_ID IN ({quoted})", "outFields": "PARCEL_ID,ACT_YR_BLT"},
            transport=transport,
        )
        found = {
            str(f["attributes"].get("PARCEL_ID")): to_int(f["attributes"].get("ACT_YR_BLT"))
            for f in features
        }
        expiry = time.monotonic() + _FOLIO_TTL_SECONDS
        for folio in batch:
            _folio_year[folio] = (expiry, found.get(folio))
    for row in rows:
        if row["year_built"] is None:
            cached = _folio_year.get(row["parcel_id"])
            if cached and cached[0] > now:
                row["year_built"] = cached[1]


def _meck_row(feature: dict) -> Row | None:
    a = feature.get("attributes", {})
    lat, lon = _centroid(feature)
    owner = " ".join(
        " ".join(str(part).split())
        for part in (a.get("ownrfrstnme"), a.get("ownrlstnme"))
        if part and str(part).strip()
    )
    acres = to_float(a.get("totalac"))
    return _row(
        parcel_id=a.get("pid"),
        address=a.get("address"),
        city=(a.get("city") or "").title(),
        zip_code="",
        lat=lat,
        lon=lon,
        year_built=to_int(a.get("yearbuilt")),
        value=to_float(a.get("totmarkval")) or to_float(a.get("totalvalue")),
        lot_size_sqft=acres * 43_560 if acres else None,
        owner_name=owner or None,
    )


def _clark_row(feature: dict) -> Row | None:
    a = feature.get("attributes", {})
    lat, lon = _centroid(feature)
    city = {"LV": "Las Vegas", "HEND": "Henderson", "NLV": "North Las Vegas"}.get(
        str(a.get("STRCITY") or "").strip(), str(a.get("STRCITY") or "").strip().title()
    )
    lot = to_float(a.get("LOTSQFT"))
    return _row(
        parcel_id=a.get("PARCEL"),
        address=" ".join(str(part) for part in (a.get("STRNO"), a.get("STRNAME")) if part),
        city=city,
        zip_code=a.get("ZIP"),
        lat=lat,
        lon=lon,
        year_built=to_int(a.get("CONSTYR")),
        value=(to_float(a.get("LANDVAL1")) or 0.0) + (to_float(a.get("IMPVAL")) or 0.0) or None,
        lot_size_sqft=lot if lot else None,
        owner_name=(str(a.get("OWNER")).strip() if str(a.get("OWNER") or "").strip() else None),
    )


# Myers Park / Eastover anchor corridor, Charlotte NC (lon/lat WGS84).
_MYERS_PARK_ENVELOPE = {
    "xmin": -80.865,
    "ymin": 35.185,
    "xmax": -80.805,
    "ymax": 35.225,
    "spatialReference": {"wkid": 4326},
}


@dataclass(frozen=True)
class CountySource:
    market: str
    state: str
    query_url: str
    source: str
    source_page: str
    page_size: int
    out_fields: list[str]
    row_builder: RowBuilder
    # bulk scope (fetch everything once, filter in memory)
    bulk_where: str | None = None
    enrich_years: Callable[[list[Row], Any], None] | None = None
    # server-side scope (anchor WHERE + per-radius envelope queries)
    anchor_where: str | None = None
    anchor_envelope: dict | None = None
    parcels_where: str = "1=1"


COLLIER = CountySource(
    market="port-royal-naples-fl",
    state="FL",
    query_url="https://gis.collier.gov/gis/rest/services/CityViewDesktop/FeatureServer/20/query",
    source="Collier County GIS - CityView Parcels (year built via FL statewide cadastral)",
    source_page="https://maps.colliercountyfl.gov/",
    page_size=2000,
    out_fields=["FOLIO", "FULLADDRESS", "NAME1", "USECODE", "TOTALACRES", "TOTALJUSTAMOUNT", "LEGALDESC"],
    row_builder=_collier_row,
    bulk_where="LEGALDESC LIKE '%PORT ROYAL%'",
    enrich_years=_collier_enrich_years,
)

MANATEE = CountySource(
    market="bradenton-anna-maria-fl",
    state="FL",
    query_url="https://www.mymanatee.org/gisits/rest/services/opendata/General/FeatureServer/0/query",
    source="Manatee County GIS Open Data - Parcels (Anna Maria Island cities)",
    source_page="https://www.mymanatee.org/gis",
    page_size=2000,
    out_fields=[
        "PARCEL_ID", "PRIMARY_ADDRESS", "PROP_CITYNAME", "PROP_ZIP", "LAT", "LON",
        "YRBLT_RES", "JUSTVAL", "ACRES", "OWNER",
    ],
    row_builder=_manatee_row,
    bulk_where="PROP_CITYNAME IN ('ANNA MARIA','BRADENTON BEACH','HOLMES BEACH')",
)

NYS = CountySource(
    market="hamptons-ny",
    state="NY",
    query_url=(
        "https://gisservices.its.ny.gov/arcgis/rest/services/"
        "NYS_Tax_Parcels_Public/FeatureServer/1/query"
    ),
    source="NYS Tax Parcels (Public) - Suffolk County towns of East Hampton & Southampton",
    source_page="https://gis.ny.gov/tax-parcel-boundaries",
    page_size=50_000,
    out_fields=[
        "PRINT_KEY", "PARCEL_ADDR", "CITYTOWN_NAME", "LOC_ZIP", "PROP_CLASS",
        "YR_BLT", "TOTAL_AV", "FULL_MARKET_VAL", "PRIMARY_OWNER", "SQ_FT", "ACRES",
    ],
    row_builder=_nys_row,
    bulk_where="COUNTY_NAME='Suffolk' AND CITYTOWN_NAME IN ('East Hampton','Southampton')",
)

MECKLENBURG = CountySource(
    market="charlotte-nc",
    state="NC",
    query_url=(
        "https://meckgis.mecklenburgcountync.gov/server/rest/services/"
        "TaxParcel_camadata/FeatureServer/0/query"
    ),
    source="Mecklenburg County Tax Parcel CAMA data (Myers Park / Eastover corridor)",
    source_page="https://polaris.mecklenburgcountync.gov/",
    page_size=2000,
    out_fields=[
        "pid", "yearbuilt", "totmarkval", "totalvalue", "ownrlstnme", "ownrfrstnme",
        "address", "city", "totalac", "heatedarea",
    ],
    row_builder=_meck_row,
    anchor_where="city='CHARLOTTE' AND yearbuilt>={min_year} AND totmarkval>={min_price}",
    anchor_envelope=_MYERS_PARK_ENVELOPE,
    parcels_where="city='CHARLOTTE'",
)

CLARK = CountySource(
    market="las-vegas-henderson-nv",
    state="NV",
    query_url=(
        "https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/"
        "CC_PARCELS_SHP/FeatureServer/1/query"
    ),
    source="Clark County assessor tax roll (via City of Henderson GIS)",
    source_page="https://www.cityofhendersonnv.gov/government/departments/information_technology_services/gis",
    page_size=2000,
    out_fields=[
        "PARCEL", "OWNER", "CONSTYR", "LANDVAL1", "IMPVAL", "STRNO", "STRNAME",
        "STRCITY", "ZIP", "LOTSQFT", "SALEPRICE", "SALEDATE",
    ],
    row_builder=_clark_row,
    # Nevada taxable value runs ~1/3-1/2 of market value; anchor thresholds are
    # user-tunable per run.
    anchor_where=(
        "(LANDVAL1+IMPVAL)>={min_price} AND CONSTYR>={min_year} "
        "AND STRCITY IN ('LV','HEND')"
    ),
    parcels_where="STRCITY IN ('LV','HEND')",
)

COUNTY_SOURCES: dict[str, CountySource] = {
    "collier": COLLIER,
    "manatee": MANATEE,
    "nys": NYS,
    "mecklenburg": MECKLENBURG,
    "clark": CLARK,
}
