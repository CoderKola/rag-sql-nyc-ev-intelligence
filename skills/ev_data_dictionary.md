# NYC EV Charging Dataset — Official Data Dictionary (NYC DOT)

Source: NYC Open Data data dictionary for dataset `kj7g-u4gp`
Agency: Department of Transportation (DOT)
Update frequency: Daily (both publishing and underlying data)
URL: https://data.cityofnewyork.us/d/kj7g-u4gp

Each row is one location/usage record for an EV charger at an NYC municipal lot or garage.

---

## Column Definitions

### Date
Date of the transaction. Format in source: DD-MM-YY.

### Station Name
Unique identifier for the EV charger unit. Naming conventions by hardware manufacturer:
- `BTCE####` — BTC Power charger (btcpower.com)
- `EV####` — DC fast charger, multiple manufacturers (BTC Power or Tritium)
- `EVB####` — EVB charger (evb.com)
- Six-digit numbers (e.g. `101013`) — unknown manufacturer
- `EVX1420` / `EVX1420z` — EVX charger (evx.tech)
- `DELETED` — charger is no longer active

### Location Name
Name of the municipal lot or garage. Blank when session status is Disconnected (charge not completed).

### Country
Country where the charger is located. Blank when session status is Disconnected.

### Charge Box ID
Unique identifier for the charger box hardware. Differs from Station Name for some units:
- `BTCE####`, `EV####` — same as Station Name
- `EVB-P#######` — EVB charger box format
- Station `101336` → `veefil-602200188`
- Station `101337` → `veefil-602200189`
- Station `101338` → `veefil-602200190`
- `EVX1420` → `1EO2-1-2138-00116`
- `EVX1420z` → `1EO1-1-2005-00059`

### Connector ID
Which physical plug on the charger unit was used.
- `1` — charger port 1
- `2` — charger port 2
Always stored as a string, not an integer.

### Driver ID
Unique ID assigned to the charging session. Blank when the session was started with a credit card rather than the EV Connect app (or another smartphone application). Driver ID and ID Tag may be identical for the same session.

### ID Tag
Unique tag for the charging session. May be the same value as Driver ID.

### Connected Time
Time the charger was physically plugged in to the vehicle. Format: HH:MM:SS (time-of-day only, no date component).

### Disconnected Time
Time the charger was unplugged from the vehicle. Format: HH:MM:SS (time-of-day only, no date component). Sessions that cross midnight will have disconnected_time earlier than connected_time — never subtract these fields for duration.

### Charge Duration (min)
Number of minutes the charger was actively transferring energy.

### Connected Duration (min)
Number of minutes the vehicle was physically connected (includes idle time after charging stopped). Always ≥ Charge Duration.

### Energy Provided (kWh)
Kilowatt-hours delivered during the session.

### Session Status
Status of the charging session. Values in the source data dictionary:
- `PAID` — transaction completed, payment processed
- `ROAMING` — session initiated via a partner app (ChargePoint, FLO, etc.) rather than EV Connect
- `DISCONNECTED` — charging session did not connect (vehicle unplugged before completion)
- `Invalid` — transaction not completed (present in dictionary; rare or absent in current dataset)
- `Aborted` — transaction cancelled (present in dictionary; rare or absent in current dataset)

Note: The current dataset (240k sessions through May 2026) contains only PAID (91.7%), ROAMING (6.7%), and DISCONNECTED (1.6%). Invalid and Aborted do not appear in practice.

### Invalidity Reason
Reason for an invalid session. Blank when not applicable. Possible values:
- `CHARGE_SESSION_ABORTED`
- `MAX_CONNECTED_TIME_EXCEEDED`
- `MAX_ENERGY_EXCEEDED`
- `NO_ENERGY_DISPENSED`
- `ZERO_CHARGING_TIME`
- `ZERO_CONNECTED_TIME`

This column was dropped at ingest (99.6% null, remainder literal "NULL") and is not present in the working dataset.

---

## Dataset Purpose

PlugNYC is NYC DOT's public EV charging network at municipal parking garages. Data is collected automatically by the chargers themselves, tracking datapoints including charge rates and times. Intended use cases: locating a charger, identifying the most frequently used chargers, and finding the best time to locate a vacant spot.
