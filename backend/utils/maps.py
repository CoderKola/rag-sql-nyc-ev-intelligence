import json
import re

from ..data.locations import LOCATION_COORDS

_MAP_PALETTES: dict[str, tuple[str, str, str]] = {
    "sessions":   ("#AECBFF", "#2563EB", "#1E40AF"),
    "energy":     ("#86EFAC", "#16A34A", "#14532D"),
    "duration":   ("#FCD34D", "#D97706", "#92400E"),
    "growth":     ("#5EEAD4", "#0D9488", "#134E4A"),
    "roaming":    ("#C4B5FD", "#7C3AED", "#4C1D95"),
    "connectors": ("#A5B4FC", "#4F46E5", "#312E81"),
}

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def extract_map_style(text: str) -> dict | None:
    m = re.search(r"```map_style\n({.*?})\n```", text, re.DOTALL)
    if not m:
        return None
    try:
        raw = json.loads(m.group(1))
        palette_key = raw.get("palette", "sessions")
        low, mid, high = _MAP_PALETTES.get(palette_key, _MAP_PALETTES["sessions"])
        return {"low": low, "mid": mid, "high": high, "metric_col": raw.get("metric")}
    except Exception:
        return None


def _preferred_metric(df, exclude: tuple = (), preferred: str | None = None) -> str | None:
    numeric_cols = [
        c for c in df.columns
        if df[c].dtype.kind in ("i", "f")
        and c not in ("latitude", "longitude", "session_year", "session_month", "connector_id", *exclude)
    ]
    if not numeric_cols:
        return None
    if preferred and preferred in numeric_cols:
        return preferred
    return next(
        (c for c in numeric_cols if any(k in c for k in ("count", "session", "energy", "kwh", "duration"))),
        numeric_cols[0],
    )


def _build_points(df, metric: str) -> list[dict]:
    points = []
    for _, row in df.iterrows():
        loc = row["location_name_clean"]
        if not loc or loc != loc:
            continue
        coords = LOCATION_COORDS.get(str(loc))
        if not coords:
            continue
        val = row[metric]
        points.append({
            "location": str(loc),
            "lat": coords[0],
            "lng": coords[1],
            "value": float(val) if val == val else 0.0,
            "metric": metric,
        })
    return points


def _fmt_month_year(period_key: str) -> str:
    """'2023-04' → 'Apr 2023'"""
    try:
        y, m = period_key.split("-")
        return f"{_MONTH_ABBR[int(m) - 1]} {y}"
    except Exception:
        return period_key


def extract_map_time_series(df, preferred: str | None = None) -> dict | None:
    """Return animated map payload when results span multiple time periods per location.
    Priority: month-year (both columns) > year-only > month-only.
    """
    if "location_name_clean" not in df.columns:
        return None

    has_year = "session_year" in df.columns
    has_month = "session_month" in df.columns

    if has_year and has_month and (df["session_year"].nunique() > 1 or df["session_month"].nunique() > 1):
        df = df.copy()
        df["_period"] = (
            df["session_year"].astype(int).astype(str) + "-"
            + df["session_month"].astype(int).astype(str).str.zfill(2)
        )
        group_col = "_period"
        time_label = "month"
        exclude = ("session_year", "session_month", "_period")
        raw_periods = sorted(df["_period"].dropna().unique().tolist())
        period_labels = [_fmt_month_year(p) for p in raw_periods]

    elif has_year and df["session_year"].nunique() > 1:
        group_col = "session_year"
        time_label = "year"
        exclude = ("session_year",)
        raw_periods = sorted(df["session_year"].dropna().unique().tolist())
        period_labels = [str(int(p)) for p in raw_periods]

    elif has_month and df["session_month"].nunique() > 1:
        group_col = "session_month"
        time_label = "month"
        exclude = ("session_month",)
        raw_periods = sorted(df["session_month"].dropna().unique().tolist())
        period_labels = [_MONTH_ABBR[int(p) - 1] for p in raw_periods]

    else:
        return None

    metric = _preferred_metric(df, exclude=exclude, preferred=preferred)
    if not metric:
        return None

    frames = []
    for period in raw_periods:
        pts = _build_points(df[df[group_col] == period], metric)
        if pts:
            frames.append(pts)

    if len(frames) < 2:
        return None

    return {
        "periods": period_labels,
        "frames": frames,
        "metric": metric,
        "time_col": time_label,
    }


def extract_map_data(df, preferred: str | None = None) -> list[dict] | None:
    if "location_name_clean" not in df.columns:
        return None
    metric = _preferred_metric(df, preferred=preferred)
    if not metric:
        return None
    points = _build_points(df, metric)
    return points if points else None


def extract_map_payload(df, preferred_metric: str | None = None) -> tuple[list[dict] | None, dict | None]:
    """Returns (static_points, time_series). Prefers time series when available."""
    ts = extract_map_time_series(df, preferred=preferred_metric)
    if ts:
        return ts["frames"][-1], ts
    return extract_map_data(df, preferred=preferred_metric), None
