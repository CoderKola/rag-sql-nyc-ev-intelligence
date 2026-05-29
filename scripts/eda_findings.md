# EDA Findings — NYC EV Charging Data (Municipal Lots)

## Sample Data (10 rows)

| date | location_name_clean | station_name | connector_id | connected_time | disconnected_time | charge_duration_min | energy_provided_kwh | idle_time_min | session_status | driver_id | session_year |
|:-----|:--------------------|-------------:|-------------:|:---------------|:------------------|--------------------:|--------------------:|--------------:|:---------------|:----------|-------------:|
| 2025-08-21 | Jerome Gun Hill Road Municipal Parking Garage | 101013 | 1 | 19:10:54 | 07:11:12 | 720.30 | 41.37 | 0.00 | PAID | 4a37c773… | 2025 |
| 2025-08-21 | Jerome Gun Hill Road Municipal Parking Garage | 101014 | 1 | 16:53:00 | 20:29:07 | 160.10 | 15.81 | 56.02 | PAID | 7fa6b416… | 2025 |
| 2025-08-21 | Jerome Gun Hill Road Municipal Parking Garage | 101016 | 1 | 23:08:38 | 09:33:03 | 570.67 | 31.87 | 53.75 | PAID | 97b09152… | 2025 |
| 2025-08-21 | Jerome Gun Hill Road Municipal Parking Garage | 101016 | 1 | 18:36:40 | 22:47:25 | 250.42 | 24.14 | 0.33 | PAID | 43d4f216… | 2025 |
| 2025-08-21 | Jerome Gun Hill Road Municipal Parking Garage | 101022 | 1 | 07:20:44 | 15:09:45 | 465.32 | 21.85 | 3.70 | PAID | 5fc5a8cf… | 2025 |
| 2025-08-21 | Bay Ridge Municipal Parking Garage | 101027 | 1 | 18:58:41 | 07:50:53 | 275.52 | 26.42 | 496.68 | PAID | 5ab38606… | 2025 |
| 2025-08-21 | Delancey and Essex Municipal Parking Garage | 101030 | 1 | 13:28:05 | 17:32:17 | 225.15 | 23.12 | 19.05 | PAID | 427cebb5… | 2025 |
| 2025-08-21 | Delancey and Essex Municipal Parking Garage | 101031 | 1 | 11:10:16 | 04:24:07 | 660.48 | 29.39 | 373.37 | PAID | b2104fd7… | 2025 |
| 2025-08-21 | Delancey and Essex Municipal Parking Garage | 101086 | 1 | 13:05:06 | 01:31:37 | 295.23 | 21.85 | 451.28 | PAID | 62e8f632… | 2025 |

> Columns omitted from sample: `location_name` (raw, use `location_name_clean`), `country`, `charge_box_id`, `id_tag`, `socrata_id`, `session_month`, `flag_zero_energy`

---

**Dataset:** data.cityofnewyork.us / kj7g-u4gp  
**Rows:** 240,012  **Cols:** 20 (after ingest cleaning)  
**Date range:** 2021-07-31 → 2026-05-26

---

## Null Rates

| Column | Null % | Note |
|--------|--------|------|
| `country` | 33.5% | Always "USA" when present — carries no info, do not filter on it |
| `driver_id` | 4.6% | Anonymous/guest sessions; nulls occur only in PAID sessions |
| `location_name_clean` | 0.01% | 29 rows where raw `location_name` = "N/A" |
| All others | 0% | No other missing data |

---

## Session Status

| Status | Count | % |
|--------|-------|---|
| PAID | 220,061 | 91.7% |
| ROAMING | 16,012 | 6.7% |
| DISCONNECTED | 3,939 | 1.6% |

- **PAID**: Standard completed session, payment processed.
- **ROAMING**: Session via a charging network partner. Roaming drivers always have a `driver_id` (0% null among ROAMING); median energy 16.7 kWh (slightly lower than PAID).
- **DISCONNECTED**: Session terminated without completion — vehicle unplugged before payment processed (fault, user error, or early departure). Still delivers a median 16 kWh.
- For total utilization queries, include PAID + ROAMING and exclude DISCONNECTED unless explicitly asked.

---

## Location Name (Deduplication Required)

The raw `location_name` column has **22 unique string values** for **10 distinct physical facilities** — the same location appears with/without a short code prefix (e.g., `"CSQ - Court Square Municipal Parking Garage"` vs `"Court Square Municipal Parking Garage"`), and with minor spelling variations. The `location_name_clean` column normalizes all variants. **Always use `location_name_clean`.**

| Canonical Name | Sessions |
|----------------|----------|
| Court Square Municipal Parking Garage | 71,775 |
| Delancey and Essex Municipal Parking Garage | 63,061 |
| Queens Borough Hall Municipal Parking Garage | 57,935 |
| Jerome 190th Street Municipal Parking Garage | 14,288 |
| Bay Ridge Municipal Parking Garage | 12,609 |
| Jerome Gun Hill Road Municipal Parking Garage | 7,980 |
| Queensboro Hall | 5,335 |
| St. George Courthouse Municipal Parking Garage | 4,957 |
| Queens Family Court Municipal Parking Garage | 2,042 |
| Hunts Point Municipal Parking Field | 1 |
| (unknown / N/A) | 29 |

---

## Connector ID

VARCHAR string `'1'` or `'2'` (not an integer). Always use string literals in SQL: `WHERE connector_id = '1'`.  
- Connector 1: 139,789 sessions (58.2%)  
- Connector 2: 100,223 sessions (41.8%)

---

## Numeric Distributions

### `charge_duration_min` (active charging time)
| Stat | Value |
|------|-------|
| min | 0.05 min |
| median | 50.2 min |
| mean | 168.1 min |
| p95 | 679.9 min (~11 hrs) |
| p99 | 1,182 min (~20 hrs) |
| max | 9,921 min (~165 hrs) |

Mean/median ratio = 3.3x — heavily right-skewed by long overnight sessions. **Use MEDIAN for typical session analysis.** Values above p99 (~20 hrs) are vehicles left for multiple days.

### `connected_duration_min` (total plug-in time including idle)
| Stat | Value |
|------|-------|
| median | 50.8 min |
| mean | 224.8 min |
| p99 | 1,821 min |
| max | 10,044 min |

Always ≥ `charge_duration_min`. Use for parking occupancy analysis.

### `energy_provided_kwh`
| Stat | Value |
|------|-------|
| zeros | 44 sessions (0.02%) |
| median | 19.8 kWh |
| mean | 22.8 kWh |
| p95 | 55.4 kWh |
| p99 | 74.0 kWh |
| max | 476.1 kWh |

Mean/median ratio = 1.15 — relatively symmetric. AVG is acceptable. Outliers above p99 (74 kWh) are DC fast chargers or multi-day sessions. The 44 zero-energy sessions are all extremely short (< 5 min, mean 0.67 min) — exclude with `WHERE energy_provided_kwh > 0` for energy analysis.

---

## Idle Time (`idle_time_min = connected_duration_min − charge_duration_min`)

- 81.5% of sessions have **zero idle time** (vehicle left immediately after charging).
- 18.2% of sessions have idle time > 0 (43,578 sessions).
- Among idle sessions: median idle = **158.8 min**, mean = **312.1 min**.
- Mean idle across all sessions: 56.7 min.
- Idle time is a key metric for parking overstay analysis.

---

## Time-of-Day Columns

`connected_time` and `disconnected_time` are stored as **VARCHAR strings** in `'HH:MM:SS'` format. They are **time-of-day only** — there is no date component. Sessions that cross midnight will have `disconnected_time < connected_time`.

- **Never subtract times directly** to compute duration — use `charge_duration_min` instead.
- To extract hour: `CAST(substr(connected_time, 1, 2) AS INTEGER)` or `connected_time::TIME`.

---

## Session Volume by Year

| Year | Sessions | Note |
|------|----------|------|
| 2021 | 3,606 | Partial year (from July) |
| 2022 | 17,275 | |
| 2023 | 40,115 | |
| 2024 | 84,611 | Full year, peak so far |
| 2025 | 69,166 | Full year |
| 2026 | 25,239 | Partial year (through May) |

Strong year-over-year growth 2021→2024. **2026 data is partial — always note this when reporting 2026 totals.**

2024→2025 apparent decline (-18%) is almost entirely Delancey & Essex (-12,718 sessions, -50.6%). Other lots are flat or growing. Queensboro Hall closed in early 2024.

### 2024 vs 2025 by location

| Location | 2024 | 2025 | Delta | % Change |
|----------|------|------|-------|----------|
| Delancey and Essex | 25,127 | 12,409 | −12,718 | −50.6% |
| Court Square | 24,730 | 21,879 | −2,851 | −11.5% |
| Queens Borough Hall | 22,991 | 22,511 | −480 | −2.1% |
| Bay Ridge | 3,442 | 3,358 | −84 | −2.4% |
| Jerome 190th Street | 4,127 | 3,802 | −325 | −7.9% |
| Queensboro Hall | 65 | 0 | −65 | −100% |
| Queens Family Court | 527 | 598 | +71 | +13.5% |
| St. George Courthouse | 922 | 1,203 | +281 | +30.5% |
| Jerome Gun Hill Road | 2,680 | 3,376 | +696 | +26.0% |

---

## Charger Hardware Tiers

Station name prefixes map to hardware type and charging speed:

| Prefix | Manufacturer | Charge type | Lots |
|--------|-------------|-------------|------|
| `EV####` | BTC Power / Tritium (DC fast) | Fast (~30 min median) | Court Square, Delancey & Essex |
| `EVB####` | EVB | Level 2 | Various |
| `BTCE####` | BTC Power | Level 2 | Various |
| `EVX####` | EVX | Level 2 | Various |
| Six-digit (e.g. `101013`) | Unknown | Level 2 | Jerome Gun Hill, Jerome 190th, QBH, others |
| `101336–101338` (veefil charge_box_id) | Veefil | DC fast (~28 min median) | Queens Borough Hall |

**DC fast charger lots (data-confirmed):**
- **Court Square**: 4 EV-prefix stations → 55,200 sessions, median 30 min, avg 22.6 kWh
- **Delancey & Essex**: 4 EV-prefix stations → 48,398 sessions, median 30 min, avg 22.2 kWh
- **Queens Borough Hall (veefil)**: 3 stations (101336–338) → 47,997 sessions, median 28 min, avg 23.8 kWh

**Level 2 lots (data-confirmed):**
- Jerome Gun Hill Road: six-digit stations, median 288–306 min, avg 20–22 kWh — Level 2 behavior
- Jerome 190th Street: median 318 min, avg 22.7 kWh
- Bay Ridge: median 313 min, avg 21.3 kWh
- Queens Family Court: median 138–156 min, avg 8.8–9.5 kWh — lowest energy in program

---

## Connector 1 vs Connector 2

| Connector | Sessions | Median charge (min) | Avg idle (min) |
|-----------|----------|---------------------|----------------|
| 1 | 139,789 | 128.7 | 97.6 |
| 2 | 100,223 | 28.8 | 0.7 |

The difference reflects which locations use each connector number, not a meaningful difference between the two ports. DC fast charger lots generate most connector 2 traffic. Bay Ridge, Jerome 190th Street, Jerome Gun Hill, Queens Family Court, Queensboro Hall, and St. George are connector 1 only (or nearly so).

---

## Idle Time by Location

| Location | Total sessions | Sessions with idle | Idle % | Median idle (idle only) |
|----------|---------------|-------------------|--------|------------------------|
| Bay Ridge | 12,572 | 6,536 | 52.0% | 239 min |
| Jerome 190th Street | 14,028 | 6,782 | 48.3% | 213 min |
| Queensboro Hall | 5,323 | 2,454 | 46.1% | 54 min |
| St. George Courthouse | 4,947 | 1,963 | 39.7% | 146 min |
| Queens Family Court | 2,033 | 707 | 34.8% | 141 min |
| Jerome Gun Hill Road | 7,973 | 2,305 | 28.9% | 70 min |
| Delancey and Essex | 60,964 | 9,398 | 15.4% | 63 min |
| Court Square | 70,457 | 10,179 | 14.4% | 235 min |
| Queens Borough Hall | 57,746 | 2,788 | 4.8% | 225 min |

Queens Borough Hall has the lowest idle rate (4.8%) despite having the highest Court Square idle median (235 min among those who do stay idle). Bay Ridge and Jerome 190th Street have the most overstay problems (>48% of sessions have idle time).

---

## Usage Patterns

**Day of week**: Nearly flat — Friday 15.1%, Tuesday 13.6% (lowest). Range of only 1.5pp. Municipal lot charging is not weekday-commuter-only.

**Time of day**: No sharp peak. Evening 18–21h slightly elevated (~5.5%/hr). Lowest 3–5 AM (~2%/hr). Charging occurs around the clock.

**Seasonality (2022–2024 average)**: December highest (4,914 avg sessions/month), March lowest (2,981). Summer (Jun–Sep) elevated.

---

## ROAMING Share by Location

| Location | ROAMING % |
|----------|-----------|
| Delancey and Essex | 8.9% |
| Court Square | 8.6% |
| Jerome 190th Street | 7.8% |
| Queensboro Hall | 7.5% |
| Queens Family Court | 4.7% |
| Queens Borough Hall | 4.0% |
| St. George Courthouse | 3.3% |
| Bay Ridge | 0.7% |
| Jerome Gun Hill Road | 0.7% |

---

## Credit Card vs App Sessions

| Payment type | Sessions | Median kWh | Median charge (min) |
|-------------|----------|------------|---------------------|
| App (has driver_id) — PAID | 211,578 | 19.8 | 52 |
| App (has driver_id) — ROAMING | 16,012 | 16.7 | 38 |
| Credit card (no driver_id) — PAID | 8,483 | 34.9 | 52 |

Credit card PAID sessions have notably higher median energy (34.9 kWh vs 19.8 kWh for app sessions). Likely reflects DC fast charger usage — drivers at fast-charging lots may prefer tap-to-pay over app sessions.

---

## Driver Stats

- 17,909 unique drivers (non-null `driver_id`)
- 11,018 sessions with no `driver_id` (credit card payment)
- Median sessions per driver: **1** (most drivers charge once)
- Max sessions by a single driver: **1,675**
- **Fleet concentration**: Top 10 drivers = 5.7% of identified sessions; Top 50 = 19.4%; Top 100 = 31.8%
- **Fleet loyalty**: Top 5 drivers each charge at a single location (97–100% of their sessions)

---

## Station vs. Charge Box ID

- `station_name`: string, 140 unique — use for station-level analysis
- `charge_box_id`: 141 unique — equals `station_name` for most stations; uses `'veefil-XXXXXXXXX'` format for the 3 DC fast stations at Queens Borough Hall (101336→veefil-602200188, 101337→veefil-602200189, 101338→veefil-602200190)
- 96,523 rows where `charge_box_id ≠ station_name` — do not equate or join these columns

---

## Key SQL Pitfalls

1. Use `location_name_clean` — never `location_name` — for filtering and grouping
2. `connector_id` is VARCHAR `'1'`/`'2'` — use string literals, not integers
3. `connected_time` / `disconnected_time` are time-of-day strings — no date arithmetic
4. Use `session_year` for year filtering, not `strftime` on `date`
5. Do not filter on `country` — 33.5% null, all sessions are from NYC regardless
6. `invalidity_reason` was dropped at ingest (99.6% null, 0.4% literal "NULL") — not in schema
7. For energy queries, add `WHERE energy_provided_kwh > 0` to exclude 44 zero sessions
8. 2026 data is partial through May — caveat any 2026 totals
9. Queensboro Hall has been offline since Feb 2024 — exclude from "current" state analysis
10. Connector 1 vs 2 comparison is not meaningful across locations — the difference reflects hardware/location mix, not port quality
