"""
EDA for NYC EV Charging Data (Municipal Lots) — kj7g-u4gp
Reads from the local parquet. Run from the project root:
  python scripts/eda.py
"""
import os
import sys

import duckdb
import pandas as pd

PARQUET = os.getenv("PARQUET_PATH", "./data/parquet/nyc_ev_charging.parquet")


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main() -> None:
    if not os.path.exists(PARQUET):
        print(f"Parquet not found at {PARQUET}. Run: python -m backend.ingest")
        sys.exit(1)

    df = pd.read_parquet(PARQUET)
    con = duckdb.connect()
    con.execute(f"CREATE VIEW ev AS SELECT * FROM read_parquet('{PARQUET}')")

    # ── Shape & dtypes ────────────────────────────────────────
    _section("Shape & dtypes")
    print(f"Rows: {len(df):,}   Cols: {df.shape[1]}")
    print()
    print(df.dtypes.to_string())

    # ── Null rates ────────────────────────────────────────────
    _section("Null rates")
    nulls = df.isnull().sum()
    rates = nulls / len(df) * 100
    for col in df.columns:
        bar = "█" * int(rates[col] / 5)
        print(f"  {col:<30} {nulls[col]:>8,}  ({rates[col]:5.1f}%)  {bar}")

    # ── Categoricals ──────────────────────────────────────────
    _section("session_status — value counts")
    print(df["session_status"].value_counts(dropna=False).to_string())

    _section("connector_id — value counts")
    print(df["connector_id"].value_counts(dropna=False).to_string())

    _section("country — value counts")
    print(df["country"].value_counts(dropna=False).to_string())

    _section("location_name_clean — session counts")
    loc = (
        df.groupby("location_name_clean", dropna=False)
        .size()
        .sort_values(ascending=False)
    )
    print(loc.to_string())

    # ── Numeric distributions ──────────────────────────────────
    num_cols = ["charge_duration_min", "connected_duration_min", "energy_provided_kwh", "idle_time_min"]
    for col in num_cols:
        _section(f"{col} — distribution")
        s = df[col].dropna()
        print(f"  count  {len(s):>12,}")
        print(f"  zeros  {(s == 0).sum():>12,}  ({(s == 0).mean() * 100:.2f}%)")
        print(f"  min    {s.min():>12.3f}")
        print(f"  p1     {s.quantile(0.01):>12.3f}")
        print(f"  p5     {s.quantile(0.05):>12.3f}")
        print(f"  median {s.median():>12.3f}")
        print(f"  mean   {s.mean():>12.3f}")
        print(f"  p95    {s.quantile(0.95):>12.3f}")
        print(f"  p99    {s.quantile(0.99):>12.3f}")
        print(f"  p99.9  {s.quantile(0.999):>12.3f}")
        print(f"  max    {s.max():>12.3f}")

    # ── Date range & yearly volume ────────────────────────────
    _section("Date range")
    print(f"  min date: {df['date'].min()}")
    print(f"  max date: {df['date'].max()}")

    _section("Sessions by year")
    yearly = df.groupby("session_year").size().sort_index()
    for yr, cnt in yearly.items():
        bar = "▓" * (cnt // 2000)
        print(f"  {yr}  {cnt:>7,}  {bar}")

    _section("Sessions by year × location")
    yl = (
        df.groupby(["session_year", "location_name_clean"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    print(yl.to_string())

    # ── Energy by status ──────────────────────────────────────
    _section("energy_provided_kwh by session_status")
    print(
        df.groupby("session_status")["energy_provided_kwh"]
        .agg(["count", "median", "mean", "max"])
        .round(2)
        .to_string()
    )

    # ── Idle time ─────────────────────────────────────────────
    _section("Idle time analysis")
    has_idle = df["idle_time_min"] > 0.1
    print(f"  Sessions with any idle time: {has_idle.sum():,} ({has_idle.mean() * 100:.1f}%)")
    print(f"  Mean idle (all sessions):    {df['idle_time_min'].mean():.1f} min")
    print(f"  Mean idle (idle only):       {df.loc[has_idle, 'idle_time_min'].mean():.1f} min")
    print(f"  Median idle (idle only):     {df.loc[has_idle, 'idle_time_min'].median():.1f} min")

    # ── Zero-energy sessions ──────────────────────────────────
    _section("Zero-energy sessions")
    zero = df[df["flag_zero_energy"]]
    print(f"  Count: {len(zero):,}  ({len(zero) / len(df) * 100:.3f}%)")
    if len(zero):
        print(zero[["session_status", "charge_duration_min"]].describe().round(3).to_string())

    # ── Driver analysis ───────────────────────────────────────
    _section("Driver stats")
    print(f"  Unique drivers (non-null):  {df['driver_id'].nunique():,}")
    print(f"  Null driver_id rows:        {df['driver_id'].isna().sum():,}")
    sessions_per_driver = df.dropna(subset=["driver_id"]).groupby("driver_id").size()
    print(f"  Median sessions/driver:     {sessions_per_driver.median():.0f}")
    print(f"  Max sessions/driver:        {sessions_per_driver.max():,}")
    top10 = sessions_per_driver.nlargest(10)
    print(f"  Top 10 driver session counts:\n{top10.to_string()}")

    print("\n")


if __name__ == "__main__":
    main()
