# EV Analyst Reasoning Framework

Use this when interpreting query results. The goal is to produce findings an NYC transit planner or infrastructure manager would act on — not a recitation of numbers.

## Session filters — the default decision
- Revenue / billing question → PAID only
- Utilization / capacity question → PAID + ROAMING (charger was occupied regardless of who paid)
- Fault / reliability question → DISCONNECTED only or include all
- General "how much charging" → PAID + ROAMING, note DISCONNECTED separately

## Energy — what the numbers mean
Median session = ~20 kWh. That is roughly 60–80 miles of range added. If a user asks "is that a lot?", yes — it covers a typical daily commute round-trip.

DC fast charger lots (Court Square EV-prefix stations, Delancey & Essex EV-prefix stations, Queens Borough Hall veefil 101336–338) deliver similar energy per session (~20–23 kWh) but in 28–30 min vs 290–410 min for Level 2 lots. Energy per session is nearly the same across lot types; what differs is throughput — a DC fast charger can serve 10x more vehicles per day than a Level 2 station delivering the same kWh per session. When comparing lots, use sessions-per-station as the throughput metric, not average kWh.

Queens Family Court is a notable outlier with median 8.8 kWh per session — significantly lower than all other lots. Its BTCE and EVB chargers appear to be lower-power units or the lot sees shorter dwell-time visits.

Mean energy (22.8 kWh) is 15% above median — right-skewed by long overnight sessions. For "typical session" use median. For "total kWh delivered to the grid" use sum.

## Idle time — what it means operationally
Idle time is lost revenue and blocked capacity. An idle vehicle is a charger that cannot serve the next driver. If a location has high median idle time (>120 min), the practical implication is that spot turnover is slow — the lot may need enforcement or pricing incentives to clear vehicles. This is an actionable infrastructure insight, not just a statistic.

Median idle (among sessions with any idle time) = 158.8 min. Sessions with zero idle = 81.5%. Both numbers together tell the story: most drivers disconnect promptly, but the minority who stay add significant lock-up time.

## Growth — how to frame year-over-year
The program grew 2021→2024 every year. 2025 vs 2024 looks like an 18% decline (69k vs 85k) but the drop is concentrated entirely at Delancey & Essex (-12,718 sessions, -50.6%), which peaked mid-2024 and reverted to 2023 levels. Jerome Gun Hill Road (+26%), St. George Courthouse (+30.5%), and Queens Borough Hall (-2.1%) were flat or growing. Queensboro Hall effectively closed in early 2024. The 2025 "decline" is a single-location story, not a program-wide trend. 2026 is partial (through May) — always state the coverage window before citing any 2026 number.

## Driver behavior — what median=1 actually means
Most drivers have 1 session in the dataset. This does NOT mean they only charged once ever — it means the median driver in the registry is infrequent. The high-frequency tail (top drivers: 1,100–1,675 sessions) represents fleet vehicles or daily commuters. Segment by frequency when a user asks about "typical drivers" vs "power users."

## Framing findings for a non-technical audience
Lead with the operational implication, not the statistic. Not "median idle time is 158 minutes" — instead "the typical vehicle that overstays blocks the charger for 2.6 hours after its charge is complete." Numbers support the framing; they do not replace it.
