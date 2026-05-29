# NYC DOT Municipal EV Charging Program — Business Context

## What this program is
NYC DOT operates EV charging stations at municipal parking garages across New York City. This is a public infrastructure program, not a commercial charging network. The goal is to make EV charging accessible to NYC residents and workers who lack home charging (apartment dwellers, commuters) and to support the city's fleet electrification targets.

## Who uses these lots
- Daily commuters who drive to transit hubs (Court Square in LIC, Queens Borough Hall in Kew Gardens)
- Government workers at civic facilities (Queens Family Court, Queens Borough Hall)
- Residents in neighborhoods with limited home charging (Bay Ridge Brooklyn, Bay Ridge has high residential EV adoption)
- ROAMING users: drivers registered on third-party networks (ChargePoint, etc.) using interoperability to access NYC DOT chargers
- Fleet vehicles: city or contractor vehicles that charge regularly — identifiable as high-frequency driver_ids (1,000+ sessions)

## What the data represents
Each row is one charging session — a single plug-in event at one connector. A driver who charges every weekday generates ~260 rows per year. Session count is a measure of demand, not unique vehicles. Use COUNT(*) for utilization, COUNT(DISTINCT driver_id) for reach.

## What "good" looks like
- High session volume per connector = high utilization = the infrastructure is needed
- Low idle time = drivers disconnect promptly, maximizing throughput
- Growing year-over-year volume = program adoption increasing
- High energy per session = longer dwell time or fast chargers serving real range needs
- Diverse driver_ids at a location = broad community access, not just a few power users monopolizing spots

## What "bad" looks like
- High idle time at a location = charger hogging, enforcement gap
- DISCONNECTED rate above ~3% = possible hardware reliability issues at that station
- Session volume stagnant or declining at a location = underutilization, possible access or awareness problem
- One driver_id dominating a location = fleet monopolization, blocking public access

## Charger hardware tiers visible in the data

**DC fast charger stations** (short dwell, ~28–30 min median charge duration):
- Court Square: EV-prefix stations (4 stations, ~55k sessions)
- Delancey & Essex: EV-prefix stations (4 stations, ~48k sessions)
- Queens Borough Hall: veefil stations 101336–101338 (3 stations, ~48k sessions)

**Level 2 stations** (long dwell, 141–411 min median):
- All six-digit stations (101013–101085 range) at Jerome Gun Hill Road, Jerome 190th Street, and others
- BTCE, EVB, EVX prefix stations
- Queens Borough Hall non-veefil stations (median 411 min)
- Queens Family Court (lowest energy: median 8.8 kWh — BTCE/EVB chargers, appears lower-power)

DC fast charger lots and Level 2 lots deliver similar median kWh per session (~20–22 kWh). The difference is throughput, not energy: DC fast serves a vehicle in 30 min vs 5+ hours for Level 2.

## Usage patterns

**Connector 1 vs 2**: Connector 2 sessions (100k) average 29 min charge and near-zero idle. Connector 1 sessions (140k) average 129 min charge and 98 min idle. This reflects which lots use which connector number — not an intrinsic difference between the two ports. DC fast lots dominate connector 2 traffic.

**Day of week**: Remarkably flat — Friday (15.1%) and Saturday (14.7%) are the busiest days, Tuesday (13.6%) the lightest. Range is only 1.5 percentage points. Municipal EV charging is not a 9-to-5 weekday pattern.

**Time of day**: No dominant peak. Evening (18–21h) is slightly elevated (~5.5% each hour). The lowest hours are 3–5 AM (~2%). Sessions are distributed around the clock.

**Seasonality**: December is the busiest month (avg 4,914 sessions, 2022–2024). March is the lightest (avg 2,981). Summer (Jun–Sep) is also elevated.

## Fleet driver patterns
Top drivers are highly location-loyal — each of the top 5 drivers charges at essentially one location (>97% of their sessions). Top 50 drivers account for 19.4% of all identified-driver sessions. These are likely fleet vehicles or daily commuters, not random public users.

## Program status as of May 2026
- Queensboro Hall: effectively offline since Feb 2024 (0 sessions in 2025)
- Hunts Point: 1 session total — not meaningfully operational
- Active lots: Court Square, Delancey & Essex, Queens Borough Hall, Jerome 190th Street, Bay Ridge, Jerome Gun Hill Road, Queens Family Court, St. George Courthouse

## Questions this tool can and cannot answer
CAN answer: utilization trends, location comparisons, energy throughput, session patterns by time of day or year, driver frequency, idle time by location.

CANNOT answer: revenue (no pricing data in this dataset), queue wait times (no reservation data), vehicle make/model, charging speed (kW — only total kWh and duration are present), whether a charger was broken vs. just idle.
