# EV Data Gotchas — Things That Will Silently Break Analysis

These are non-obvious traps. Each one produces a query that runs without error but returns a wrong or misleading answer.

## 1. 2026 is a partial year (through May only)
Never show a 2026 total alongside full prior years without flagging it. "Sessions in 2026: 25,239" next to "2025: 69,166" looks like a 64% drop. It is not — it is 5 months vs 12. Always say "2026 data is through May 2026."

## 2. The fast-charger lots are Court Square, Delancey & Essex, and Queens Borough Hall — NOT Jerome Gun Hill
Three lots have DC fast charger stations in the data:
- **Court Square**: EV-prefix stations, median charge duration ~30 min, avg 22.6 kWh
- **Delancey & Essex**: EV-prefix stations (4 DC fast), median ~30 min, avg 22.2 kWh
- **Queens Borough Hall**: veefil stations 101336–101338, median ~28 min, avg 23.8 kWh

Jerome Gun Hill Road has six-digit stations (101013–101022) with Level 2 behavior: median ~295 min, ~20–22 kWh. If a result shows Jerome Gun Hill with high energy, that is NOT a DC fast charger effect — the energy is similar to other Level 2 lots. Never state Jerome Gun Hill has DC fast chargers based on the data.

## 3. location_name has duplicate names for the same place
The raw `location_name` column has 22 string variants for 10 physical lots. Always use `location_name_clean`. If a result shows unexpectedly low session counts for a well-known location, it may be a naming variant problem — check `location_name` directly.

## 4. Queensboro Hall and Queens Borough Hall share the same address
Both are at 80-25 126th St, Kew Gardens. They are the same physical complex logged under two names. When computing totals for the Queens Borough Hall facility, include both `location_name_clean` values if the question is about the physical site.

## 5. connector_id is the string '1' or '2', not an integer
SQL filter must be `connector_id = '1'`, not `connector_id = 1`. The integer form returns zero rows silently.

## 6. connected_time and disconnected_time are time-of-day strings only
They carry no date. A session connecting at 23:30 and disconnecting at 07:15 spans midnight — `disconnected_time < connected_time`. Never subtract these times for duration; use `charge_duration_min`. Never combine them with `date` to build a full datetime — the result is meaningless.

## 7. Connector 1 and connector 2 are not interchangeable across locations
Connector 2 sessions have a median charge duration of ~29 min and near-zero idle (avg 0.7 min). Connector 1 sessions have a median of ~129 min and 97.6 min avg idle. This is not a meaningful difference between the two ports on the same charger — it reflects which locations happen to use which connector number. DC fast charger lots (Court Square, Delancey & Essex, QBH veefil) generate most connector 2 usage. Never compare connector 1 vs 2 across the whole dataset and claim one port is "faster" or "more efficient."

## 8. Queensboro Hall has been offline since February 2024
Queensboro Hall had ~250 sessions/month through 2023 and early 2024, then abruptly dropped to 65 sessions in Jan–Feb 2024 and zero ever since. Exclude it from any analysis of "current" program state, or flag it as offline. Do not report it as an active location.

## 9. The 2025 apparent program decline is driven by one location
Total 2025 sessions (69,166) vs 2024 (84,611) looks like a 18% drop. It is almost entirely Delancey & Essex (-12,718 sessions, -50.6%). That lot peaked at ~3,000/month in mid-2024 and fell back to ~900–1,200/month through 2025. Jerome Gun Hill +26%, St. George +30.5%, Queens Borough Hall stable. Do not frame this as program-wide decline without decomposing by location.

## 10. country is 33% null for no structural reason
All sessions are from NYC regardless of whether `country` is null or 'USA'. Filtering `WHERE country = 'USA'` silently excludes one-third of all sessions. Never filter on this column.
