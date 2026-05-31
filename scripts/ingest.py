"""
Socrata → parquet + ChromaDB schema index.

Run once locally after EDA findings are confirmed.
Usage: python scripts/ingest.py
"""
import os
import re
import sys
import time

import chromadb
import httpx
import pandas as pd
from dotenv import load_dotenv
from sodapy import Socrata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.data.locations import LOCATION_COORDS

load_dotenv()

DATASET_ID = "kj7g-u4gp"
DOMAIN = "data.cityofnewyork.us"
CHROMA_PATH = os.getenv("CHROMA_PERSIST_PATH", "./data/chroma")
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
PAGE_SIZE = 50_000

_parquet_env = os.getenv("PARQUET_PATH", "./data/parquet/nyc_ev_charging.parquet")
PARQUET_PATH = (
    os.path.join(_parquet_env, "nyc_ev_charging.parquet")
    if _parquet_env.endswith(("/", os.sep)) or os.path.isdir(_parquet_env)
    else _parquet_env
)

NUM_COLS = ["charge_duration_min", "connected_duration_min", "energy_provided_kwh"]


# Canonical location names — raw data has the same facility under multiple name variants
# (with/without the short code prefix, and with slight spelling differences).
LOCATION_MAP: dict[str, str] = {
    "QBO - Queens Borough Hall Municipal Parking Garage": "Queens Borough Hall Municipal Parking Garage",
    "Queens Borough Hall Municipal Parking Garage": "Queens Borough Hall Municipal Parking Garage",
    "Queensboro Hall": "Queensboro Hall",
    "CSQ - Court Square Municipal Parking Garage": "Court Square Municipal Parking Garage",
    "Court Square Municipal Parking Garage": "Court Square Municipal Parking Garage",
    "DES - Delancey and Essex Municipal Parking Garage": "Delancey and Essex Municipal Parking Garage",
    "Delancey and Essex Municipal Parking Garage": "Delancey and Essex Municipal Parking Garage",
    "JGU - Jerome Gun Hill Road Municipal Parking Garage": "Jerome Gun Hill Road Municipal Parking Garage",
    "Jerome Gun Hill Road Municipal Parking Garage": "Jerome Gun Hill Road Municipal Parking Garage",
    "Jerome-Gun Hill Road Municipal Parking Garage": "Jerome Gun Hill Road Municipal Parking Garage",
    "BRI - Bay Ridge Municipal Parking Garage": "Bay Ridge Municipal Parking Garage",
    "Bay Ridge Municipal Parking Garage": "Bay Ridge Municipal Parking Garage",
    "JON - Jerome 190th Street Municipal Parking": "Jerome 190th Street Municipal Parking Garage",
    "JON - Jerome 190th Street Municipal Parking Garage": "Jerome 190th Street Municipal Parking Garage",
    "Jerome 190th Street Municipal Parking": "Jerome 190th Street Municipal Parking Garage",
    "Jerome 190th Street Municipal Parking Garage": "Jerome 190th Street Municipal Parking Garage",
    "St. George Courthouse": "St. George Courthouse Municipal Parking Garage",
    "St. George Courthouse Garage": "St. George Courthouse Municipal Parking Garage",
    "SGE - St. George Courthouse Garage": "St. George Courthouse Municipal Parking Garage",
    "SGE - St. George Courthouse Municipal Parking Garage": "St. George Courthouse Municipal Parking Garage",
    "QFA - Queens Family Court Municipal Garage": "Queens Family Court Municipal Parking Garage",
    "QFA - Queens Family Court Municipal Parking Garage": "Queens Family Court Municipal Parking Garage",
    "Queens Family Court Municipal Garage": "Queens Family Court Municipal Parking Garage",
    "Queens Family Court Municipal Parking Garage": "Queens Family Court Municipal Parking Garage",
    "HPO - Hunts Point Municipal Parking Field": "Hunts Point Municipal Parking Field",
    "N/A": None,
}

# Schema docs for ChromaDB. Each entry encodes the EDA finding that matters when
# writing SQL against this column. Vague descriptions are useless to the SQL LLM.
COLUMN_DOCS: dict[str, str] = {
    "date": (
        "Session date as a DATE (no time component). 0% null. "
        "Range: 2021-07-31 to 2026-05-26. Session volume grows year-over-year: "
        "2021=3,606, 2022=17,275, 2023=40,115, 2024=84,611, 2025=69,166, 2026=25,239 (partial). "
        "Use session_year for year-level aggregation, strftime('%m', date) for month. "
        "Do NOT use CURRENT_DATE or CURRENT_YEAR — always use the supplied data_year constant."
    ),
    "station_name": (
        "Numeric station identifier as a string (e.g., '101013'). 0% null. 140 unique values. "
        "Each station_name is a physical charging unit; a station can have 1 or 2 connectors "
        "(connector_id = 1 or 2). Use station_name for station-level aggregation and filtering. "
        "Do not confuse with charge_box_id, which differs for DC fast charger hardware."
    ),
    "location_name": (
        "Raw facility name as received from the source. DO NOT use for filtering or grouping — "
        "it has duplicates: the same facility appears under multiple name variants "
        "(e.g., 'Court Square Municipal Parking Garage' and 'CSQ - Court Square Municipal Parking Garage'). "
        "Always use location_name_clean for filtering, display, and GROUP BY."
    ),
    "location_name_clean": (
        "Canonical facility name normalized during ingest. 9 distinct active locations: "
        "Court Square Municipal Parking Garage (~72k sessions), "
        "Delancey and Essex Municipal Parking Garage (~63k), "
        "Queens Borough Hall Municipal Parking Garage (~58k), "
        "Bay Ridge Municipal Parking Garage (~13k), "
        "Jerome 190th Street Municipal Parking Garage (~14k), "
        "Jerome Gun Hill Road Municipal Parking Garage (~8k), "
        "Queensboro Hall (~5k), "
        "St. George Courthouse Municipal Parking Garage (~5k), "
        "Queens Family Court Municipal Parking Garage (~2k). "
        "Null for 29 rows with raw location_name = 'N/A'. "
        "Always use this column for location filtering and GROUP BY, never location_name."
    ),
    "country": (
        "Always 'USA' when not null — all sessions are from NYC municipal lots. "
        "33.52% null for no apparent reason; nulls are NOT a data quality signal. "
        "Do NOT filter on this column — it adds no information."
    ),
    "charge_box_id": (
        "Hardware charger ID. 0% null. For Level 2 chargers, equals station_name (numeric string). "
        "For DC fast charger stations (station_name '101336', '101337', etc.), uses a "
        "'veefil-XXXXXXXXX' format — different from station_name. "
        "Use station_name for station-level analysis; charge_box_id is only useful for "
        "hardware-level debugging, not analytics."
    ),
    "connector_id": (
        "Port number on the charger. VARCHAR string ('1' or '2'). 0% null. "
        "Connector '1' handles 58.2% of sessions, connector '2' handles 41.8%. "
        "Always use string literals when filtering: WHERE connector_id = '1'. "
        "Use for port-level utilization analysis. Group by station_name AND connector_id "
        "to get port-level metrics."
    ),
    "driver_id": (
        "UUID string identifying the driver account. 4.59% null (anonymous or guest sessions "
        "where the driver did not authenticate with an account). 17,909 unique drivers. "
        "Exclude nulls when computing per-driver statistics. "
        "ROAMING sessions always have a driver_id (0% null among ROAMING); "
        "nulls occur only in PAID sessions."
    ),
    "id_tag": (
        "RFID card or authentication token used to start the session. 0% null. "
        "29,810 unique values. Not meaningful for general analytics — "
        "use driver_id for driver-level analysis."
    ),
    "connected_time": (
        "Time of day when the vehicle plugged in, stored as a VARCHAR string in 'HH:MM:SS' format. "
        "This is TIME-OF-DAY ONLY — there is no date component. 0% null. "
        "To extract hour: CAST(substr(connected_time, 1, 2) AS INTEGER) or connected_time::TIME. "
        "Do NOT combine connected_time with the date column to construct a full datetime — "
        "the result will be meaningless."
    ),
    "disconnected_time": (
        "Time of day when the vehicle unplugged, stored as VARCHAR 'HH:MM:SS'. "
        "TIME-OF-DAY ONLY — no date component. 0% null. Same caveats as connected_time. "
        "Sessions that cross midnight will have disconnected_time < connected_time — "
        "do not subtract times to compute duration; use charge_duration_min instead."
    ),
    "charge_duration_min": (
        "Minutes of active energy delivery. 0% null, no zeros. "
        "Range: 0.05–9,921 min. Median 50.2 min (~50 min typical session). "
        "Mean 168 min — mean/median ratio 3.3x, heavily right-skewed by long overnight sessions. "
        "Use MEDIAN for typical session analysis; use AVG only when outliers are intentional. "
        "p95=680 min (~11 hrs), p99=1,182 min (~20 hrs). Values above p99 are likely vehicles "
        "left overnight or multiple days — flag these as outliers."
    ),
    "connected_duration_min": (
        "Minutes vehicle was physically connected (includes idle time after charging completed). "
        "Always >= charge_duration_min. 0% null. "
        "Mean idle time (connected_duration_min - charge_duration_min) = 56.7 min. "
        "18.2% of sessions have any idle time (vehicle left plugged in after charge complete). "
        "Use charge_duration_min for charging analysis; use connected_duration_min for "
        "parking occupancy analysis. idle_time_min derived column = connected - charge."
    ),
    "energy_provided_kwh": (
        "Energy delivered in kilowatt-hours (kWh). 0% null. 44 zero-energy sessions (0.02%) — "
        "these are extremely short sessions (< 5 min) that should be excluded from energy analysis "
        "with WHERE energy_provided_kwh > 0. "
        "Range: 0–476 kWh. Median 19.8 kWh, mean 22.8 kWh (mean/median ratio 1.15 — "
        "relatively symmetric; AVG is acceptable). p99 = 74 kWh; values above this are outliers "
        "(DC fast chargers or multi-day sessions). "
        "Energy varies by location: Court Square median 17.9 kWh, "
        "Jerome 190th St Garage median 34.1 kWh (DC fast chargers)."
    ),
    "session_status": (
        "Outcome of the charging session. 0% null. Three values only: "
        "'PAID' (91.7%) — standard completed session with payment processed. "
        "'ROAMING' (6.7%) — session via a charging network partner (interoperability). "
        "Roaming drivers always have a driver_id; energy median is 16.7 kWh (slightly lower than PAID). "
        "'DISCONNECTED' (1.6%) — session terminated without completion; vehicle unplugged before "
        "payment was processed (fault, user error, or early departure). "
        "Filter WHERE session_status = 'PAID' for standard sessions only. "
        "Include ROAMING alongside PAID for total utilization metrics."
    ),
    "invalidity_reason": (
        "99.58% null. The remaining 1,000 rows contain the literal string 'NULL' — not a real value. "
        "This column carries no analytical information. Do NOT use in any query."
    ),
    "session_year": (
        "Integer year extracted from date (e.g., 2021–2026). Added during ingest. "
        "Use for year-over-year aggregation: GROUP BY session_year. "
        "2026 data is partial (through May 2026) — always note this when reporting 2026 totals."
    ),
    "session_month": (
        "Integer month (1–12) extracted from date. Added during ingest. "
        "Use for seasonal analysis. Sessions are fairly evenly distributed across months "
        "(2024 range: 5,437–8,246 sessions per month, with slight summer peak)."
    ),
    "idle_time_min": (
        "Minutes vehicle sat connected after charging completed "
        "(connected_duration_min - charge_duration_min). Added during ingest. "
        "Zero means vehicle disconnected as soon as charging finished. "
        "18.2% of sessions have idle_time_min > 0. Mean idle time = 56.7 min among all sessions. "
        "Use for parking overstay analysis."
    ),
    "flag_zero_energy": (
        "Boolean: True for the 44 sessions (0.02%) where energy_provided_kwh = 0. "
        "These are extremely short sessions (< 5 min). "
        "Always filter WHERE NOT flag_zero_energy for energy analysis."
    ),
    "latitude": (
        "Latitude of the parking facility (WGS84). Added at ingest from hardcoded lookup. "
        "Null for 30 rows where location_name_clean is null or unknown. "
        "All 9 real locations have coordinates. Use with longitude for map-based analysis."
    ),
    "longitude": (
        "Longitude of the parking facility (WGS84). Added at ingest from hardcoded lookup. "
        "Null for 30 rows where location_name_clean is null or unknown. "
        "Pair with latitude for geographic queries."
    ),
}


def _fetch_all(token: str | None) -> pd.DataFrame:
    client = Socrata(DOMAIN, token, timeout=120)
    total = int(client.get(DATASET_ID, select="count(*)", limit=1)[0]["count"])
    print(f"Total rows reported by API: {total:,}")

    frames: list[pd.DataFrame] = []
    offset = 0
    while True:
        rows = client.get(
            DATASET_ID,
            select="*, :id",
            order=":id ASC",
            limit=PAGE_SIZE,
            offset=offset,
        )
        if not rows:
            break
        frames.append(pd.DataFrame.from_records(rows))
        offset += len(rows)
        pct = offset / total * 100
        print(f"  fetched {offset:>7,} / {total:,}  ({pct:.1f}%)", end="\r", flush=True)
        if len(rows) < PAGE_SIZE:
            break

    print()
    return pd.concat(frames, ignore_index=True)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={":id": "socrata_id"})

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    # Normalize time-of-day strings: raw values are "HH:MM:SS.0000000" — strip to "HH:MM:SS"
    for col in ["connected_time", "disconnected_time"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.extract(r"(\d{2}:\d{2}:\d{2})")[0]

    for col in NUM_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Canonical location name (deduplicate variant spellings)
    df["location_name_clean"] = df["location_name"].map(LOCATION_MAP)

    # Hardcoded coordinates keyed on canonical location name
    df["latitude"] = df["location_name_clean"].map(
        lambda x: LOCATION_COORDS.get(x, (None, None))[0] if x else None
    )
    df["longitude"] = df["location_name_clean"].map(
        lambda x: LOCATION_COORDS.get(x, (None, None))[1] if x else None
    )

    # Derived columns
    df["session_year"] = pd.to_datetime(df["date"], errors="coerce").dt.year.astype("Int64")
    df["session_month"] = pd.to_datetime(df["date"], errors="coerce").dt.month.astype("Int64")
    df["idle_time_min"] = df["connected_duration_min"] - df["charge_duration_min"]

    # Flags
    df["flag_zero_energy"] = df["energy_provided_kwh"] == 0

    # Drop the invalidity_reason column — 99.58% null, remaining values are literal "NULL" strings
    if "invalidity_reason" in df.columns:
        df = df.drop(columns=["invalidity_reason"])

    return df


def fetch_and_save() -> None:
    """Pull full dataset from Socrata, clean, and save as parquet."""
    if os.path.exists(PARQUET_PATH):
        print(f"Parquet already exists at {PARQUET_PATH} — skipping fetch")
        return

    token = os.getenv("SOCRATA_APP_TOKEN")
    if not token:
        print("Warning: SOCRATA_APP_TOKEN not set — unauthenticated (throttled to 1 req/s)")

    os.makedirs(os.path.dirname(os.path.abspath(PARQUET_PATH)), exist_ok=True)

    print(f"Fetching {DOMAIN}/{DATASET_ID} ...")
    t0 = time.time()
    df = _fetch_all(token)
    elapsed = time.time() - t0
    print(f"Fetched {len(df):,} rows in {elapsed:.0f}s")

    print("Cleaning ...")
    df = _clean(df)
    print(f"Clean shape: {df.shape[0]:,} rows × {df.shape[1]} cols")

    df.to_parquet(PARQUET_PATH, index=False)
    size_mb = os.path.getsize(PARQUET_PATH) / 1e6
    print(f"Saved → {PARQUET_PATH}  ({size_mb:.1f} MB)")


def _embed(text: str) -> list[float]:
    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": "nomic-embed-text", "input": text},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_URL}. "
            "Start Ollama with: ollama serve"
        )
    return resp.json()["embeddings"][0]


def _check_ollama() -> None:
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
    except Exception as exc:
        raise RuntimeError(
            f"Ollama is not running at {OLLAMA_URL}. Start with: ollama serve\n{exc}"
        )
    if not any("nomic-embed-text" in m for m in models):
        raise RuntimeError(
            "nomic-embed-text model not found. Pull it with: ollama pull nomic-embed-text"
        )


def build_chroma_index() -> None:
    """Embed column docs with nomic-embed-text via Ollama and store in ChromaDB."""
    _check_ollama()

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection("ev_charging_schema")

    existing_ids = set(collection.get(include=[])["ids"])
    new_cols = [col for col in COLUMN_DOCS if col not in existing_ids]

    if not new_cols:
        print("ChromaDB index already up to date")
        return

    ids, embeddings, documents, metadatas = [], [], [], []
    for col in new_cols:
        doc = COLUMN_DOCS[col]
        emb = _embed(doc)
        ids.append(col)
        embeddings.append(emb)
        documents.append(doc)
        metadatas.append({"column": col})
        print(f"  embedded {col}")

    collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    print(f"Added {len(ids)} schema chunks to ChromaDB at {CHROMA_PATH}")


if __name__ == "__main__":
    fetch_and_save()
    build_chroma_index()
    print("Ingest complete.")
