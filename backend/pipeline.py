import asyncio
import datetime
import json
import re

import httpx
from tabulate import tabulate

from . import budget, executor, guard, llm, query_engine, rag
from .locations import LOCATION_COORDS
from .prompts import DIRECT_PROMPT, INTERPRET_PROMPT, NEAREST_PROMPT, SQL_FIX_PROMPT, SQL_PROMPT


def _extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text.strip()


def _extract_code(text: str) -> str | None:
    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else None


_HEADER_RE = re.compile(
    r"^(#{1,3}\s+.*|(?:\*\*)?(?:answer|direct answer|python plotly (?:code|chart)|plotly chart|chart code)(?:\*\*)?\s*:?\s*)",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_code(text: str) -> str:
    text = re.sub(r"```python\n.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"```map_style\n.*?```", "", text, flags=re.DOTALL)
    text = _HEADER_RE.sub("", text)
    return text.strip()


_MAP_PALETTES: dict[str, tuple[str, str, str]] = {
    "sessions":   ("#AECBFF", "#2563EB", "#1E40AF"),
    "energy":     ("#86EFAC", "#16A34A", "#14532D"),
    "duration":   ("#FCD34D", "#D97706", "#92400E"),
    "growth":     ("#5EEAD4", "#0D9488", "#134E4A"),
    "roaming":    ("#C4B5FD", "#7C3AED", "#4C1D95"),
    "connectors": ("#A5B4FC", "#4F46E5", "#312E81"),
}


def _extract_map_style(text: str) -> dict | None:
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


_TEMPORAL_PATTERNS = re.compile(
    r"\b(this year|current year|so far this year|year to date|ytd|in \d{4})\b",
    re.IGNORECASE,
)


def _data_gap_warning(message: str, data_year_int: int) -> bool:
    current_year = datetime.date.today().year
    if data_year_int >= current_year:
        return False
    for m in re.finditer(r"\b(20\d{2})\b", message):
        if int(m.group(1)) > data_year_int:
            return True
    return bool(_TEMPORAL_PATTERNS.search(message))


_INFO_RE = re.compile(
    r"\b(rate|price|cost|how much|how to pay|payment|fee|what does it cost|"
    r"how do i|how do you|how can i|opening hour|hours|open|closed|when|"
    r"register|sign.?up|how to use|how to charge|instructions|"
    r"what is plug.?nyc|about the program|about plugnyc|"
    r"contact|phone|email|website|app|ev connect|"
    r"what charger|type of charger|level 2|dc fast|dcfc|"
    r"can i use|do i need|do i have to|is it free)\b",
    re.IGNORECASE,
)

_NEAREST_RE = re.compile(
    r"\b(nearest|closest|near me|close to|near|find.*charger|charger.*near|"
    r"where.*can.*i.*charge|find.*station|station.*near|distance|how far)\b",
    re.IGNORECASE,
)

_EXPLAIN_RE = re.compile(
    r"\b(explain|elaborate|interpret|clarify|what do (these|those|the) (numbers|results|data|figures) mean|"
    r"tell me more|more detail|break.?down (those|these|the) results|what does this (mean|show|tell)|"
    r"dig into|go deeper|unpack)\b",
    re.IGNORECASE,
)

_CONFUSION_RE = re.compile(
    r"\b("
    r"confused|confusing|i.m confused|"
    r"don.t understand|didn.t understand|do not understand|"
    r"not following|i.m not following|"
    r"lost me|you lost me|"
    r"doesn.t make sense|doesn.t add up|make sense of this|help me understand|"
    r"what do you mean|what does that mean|"
    r"analogy|metaphor|"
    r"in simpler terms|plain english|plain language|"
    r"eli5|explain like|layman|layperson|"
    r"can you rephrase|rephrase that|different way|another way|"
    r"why is|why are|why does|why did|why do|"
    r"what causes|what.s causing|"
    r"what explains|what.s the reason|"
    r"what.s driving|what drives|"
    r"what accounts for|"
    r"how does (that|this) work"
    r")\b",
    re.IGNORECASE,
)


def _needs_reasoning(message: str, history: list[dict]) -> bool:
    if _CONFUSION_RE.search(message):
        return True
    # explicit elaboration on a prior exchange — user is iterating toward understanding
    if _EXPLAIN_RE.search(message) and history:
        return True
    return False

_SQL_FROM_HISTORY_RE = re.compile(r"\[SQL used: (.*?)\]$", re.DOTALL)


def _extract_last_sql_from_history(history: list[dict]) -> str | None:
    for msg in reversed(history):
        if msg["role"] == "assistant":
            m = _SQL_FROM_HISTORY_RE.search(msg["content"])
            if m:
                return m.group(1).strip()
    return None


def _detect_route(message: str, history: list[dict]) -> str:
    if _NEAREST_RE.search(message):
        return "nearest"
    if _INFO_RE.search(message):
        return "direct"
    if _EXPLAIN_RE.search(message) and _extract_last_sql_from_history(history):
        return "explain"
    return "sql"


async def _geocode(query: str, http_client: httpx.AsyncClient) -> tuple[float, float, str] | None:
    search = query if "new york" in query.lower() or "nyc" in query.lower() else f"{query}, New York City"
    try:
        resp = await http_client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": search, "format": "json", "limit": 1},
            headers={"User-Agent": "nyc-ev-intelligence/1.0"},
            timeout=8.0,
        )
        results = resp.json()
        if results:
            r = results[0]
            label = r.get("display_name", query).split(",")[0]
            return float(r["lat"]), float(r["lon"]), label
    except Exception:
        pass
    return None


def _extract_location_query(message: str) -> str:
    patterns = [
        r"(?:closest to|nearest to|close to|near to)\s+([A-Za-z][A-Za-z0-9\s,]+?)(?:\?|$|\.)",
        r"\bnear\s+(?!me\b)([A-Za-z][A-Za-z0-9\s,]+?)(?:\?|$|\.)",
        r"\bto\s+([A-Z][A-Za-z0-9\s,]+?)(?:\?|$|\.)",
        r"\bin\s+([A-Z][A-Za-z0-9\s]+?)(?:\?|$|\.|,)",
        r"\bfrom\s+([A-Za-z][A-Za-z0-9\s,]+?)(?:\?|$|\.)",
    ]
    for pat in patterns:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            loc = m.group(1).strip().rstrip(",")
            if not re.match(r"(?i)(the|a |an |find|me|my|closest|nearest|charger|station)", loc):
                return loc
    return ""


_RESULTS_CAP = 200


def _format_results(df) -> str:
    truncated = len(df) > _RESULTS_CAP
    table = tabulate(df.head(_RESULTS_CAP), headers="keys", tablefmt="github", showindex=False)
    if truncated:
        table += f"\n\n[Note: results truncated — showing {_RESULTS_CAP} of {len(df)} rows. Interpret trends cautiously; aggregate further if needed.]"
    return table


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


def _extract_map_data(df, preferred: str | None = None) -> list[dict] | None:
    if "location_name_clean" not in df.columns:
        return None
    metric = _preferred_metric(df, preferred=preferred)
    if not metric:
        return None
    points = _build_points(df, metric)
    return points if points else None


_MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def _fmt_month_year(period_key: str) -> str:
    """'2023-04' → 'Apr 2023'"""
    try:
        y, m = period_key.split("-")
        return f"{_MONTH_ABBR[int(m) - 1]} {y}"
    except Exception:
        return period_key


def _extract_map_time_series(df, preferred: str | None = None) -> dict | None:
    """Return animated map payload when results span multiple time periods per location.
    Priority: month-year (both columns) > year-only > month-only.
    This lets the LLM control granularity via SQL grouping.
    """
    if "location_name_clean" not in df.columns:
        return None

    has_year = "session_year" in df.columns
    has_month = "session_month" in df.columns

    if has_year and has_month and (df["session_year"].nunique() > 1 or df["session_month"].nunique() > 1):
        # Month-year: combine into sortable "YYYY-MM" keys
        df = df.copy()
        df["_period"] = (
            df["session_year"].astype(int).astype(str) + "-" +
            df["session_month"].astype(int).astype(str).str.zfill(2)
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


def _extract_map_payload(df, preferred_metric: str | None = None) -> tuple[list[dict] | None, dict | None]:
    """Returns (static_points, time_series). Prefers time series when available."""
    ts = _extract_map_time_series(df, preferred=preferred_metric)
    if ts:
        return ts["frames"][-1], ts  # static = latest frame for header metadata
    return _extract_map_data(df, preferred=preferred_metric), None


def _sse(**kwargs) -> str:
    return f"data: {json.dumps(kwargs)}\n\n"


async def _handle_explain(
    message: str,
    http_client: httpx.AsyncClient,
    prior_sql: str,
    parquet_path: str,
    data_year: str,
    data_complete_year: int,
    history: list[dict],
    gap_warning: bool,
    use_reasoner: bool = False,
):
    """Re-run the prior SQL and re-interpret results for elaboration requests."""
    yield _sse(type="thinking", step="Re-running prior query…")
    result = await asyncio.to_thread(query_engine.run_query, prior_sql, parquet_path)

    if isinstance(result, str):
        # SQL failed (schema drift, etc.) — fall back to answering from history text
        if use_reasoner:
            yield _sse(type="thinking", step="Reasoning through your question…")
            _, answer, in_tok, out_tok = await llm.call_deepseek_reasoner(
                http_client,
                system=INTERPRET_PROMPT.system,
                user=f"The user asked: {message}\n\nPlease elaborate based on the prior analysis in the conversation.",
                history=history or None,
            )
            budget.log_usage("deepseek-reasoner", in_tok, out_tok)
        else:
            yield _sse(type="thinking", step="Composing answer from prior results…")
            answer, in_tok, out_tok = await llm.call_deepseek(
                http_client,
                system=INTERPRET_PROMPT.system,
                user=f"The user asked: {message}\n\nPlease elaborate based on the prior analysis in the conversation.",
                history=history or None,
            )
            budget.log_usage("deepseek-v4-flash", in_tok, out_tok)
        yield _sse(
            type="answer", answer=_strip_code(answer), sql=prior_sql,
            chart_html=None, map_data=None,
            spend=round(budget.get_monthly_spend(), 6),
            warning=budget.is_warning(), data_gap_warning=gap_warning,
            context_tokens=in_tok,
        )
        return

    if use_reasoner:
        yield _sse(type="thinking", step="Reasoning through results…")
        _, interpretation, in_tok, out_tok = await llm.call_deepseek_reasoner(
            http_client,
            system=INTERPRET_PROMPT.system,
            user=INTERPRET_PROMPT.user.format(
                user_question=message,
                sql_query=prior_sql,
                query_results=_format_results(result),
                data_year=data_year,
                data_complete_year=data_complete_year,
            ),
            history=history or None,
        )
        budget.log_usage("deepseek-reasoner", in_tok, out_tok)
    else:
        yield _sse(type="thinking", step="Interpreting results…")
        interpretation, in_tok, out_tok = await llm.call_deepseek(
            http_client,
            system=INTERPRET_PROMPT.system,
            user=INTERPRET_PROMPT.user.format(
                user_question=message,
                sql_query=prior_sql,
                query_results=_format_results(result),
                data_year=data_year,
                data_complete_year=data_complete_year,
            ),
            history=history or None,
        )
        budget.log_usage("deepseek-v4-flash", in_tok, out_tok)

    chart_html = None
    chart_code = _extract_code(interpretation)
    if chart_code:
        yield _sse(type="thinking", step="Rendering chart…")
        chart_result = await asyncio.to_thread(executor.run_chart_code, chart_code)
        if chart_result["success"]:
            chart_html = chart_result["chart_html"]

    map_style = _extract_map_style(interpretation)
    map_data, map_ts = _extract_map_payload(result, preferred_metric=map_style.get("metric_col") if map_style else None)
    yield _sse(
        type="answer", answer=_strip_code(interpretation), sql=prior_sql,
        chart_html=chart_html, map_data=map_data, map_time_series=map_ts,
        map_style={k: v for k, v in (map_style or {}).items() if k != "metric_col"} or None,
        spend=round(budget.get_monthly_spend(), 6),
        warning=budget.is_warning(), data_gap_warning=gap_warning,
        context_tokens=in_tok,
    )


async def _handle_direct(
    message: str,
    http_client: httpx.AsyncClient,
    context: str,
    history: list[dict],
    use_reasoner: bool = False,
):
    if use_reasoner:
        yield _sse(type="thinking", step="Reasoning through your question…")
        _, answer, in_tok, out_tok = await llm.call_deepseek_reasoner(
            http_client,
            system=DIRECT_PROMPT.system,
            user=DIRECT_PROMPT.user.format(retrieved_context=context, user_question=message),
            history=history or None,
        )
        budget.log_usage("deepseek-reasoner", in_tok, out_tok)
    else:
        yield _sse(type="thinking", step="Composing answer…")
        answer, in_tok, out_tok = await llm.call_deepseek(
            http_client,
            system=DIRECT_PROMPT.system,
            user=DIRECT_PROMPT.user.format(retrieved_context=context, user_question=message),
            history=history or None,
        )
        budget.log_usage("deepseek-v4-flash", in_tok, out_tok)
    yield _sse(
        type="answer", answer=answer, sql="",
        chart_html=None, map_data=None,
        spend=round(budget.get_monthly_spend(), 6),
        warning=budget.is_warning(), data_gap_warning=False,
        context_tokens=in_tok,
    )


async def _handle_nearest(
    message: str,
    http_client: httpx.AsyncClient,
    context: str,
    parquet_path: str,
    data_year: str,
    data_year_int: int,
    data_complete_year: int,
    history: list[dict],
):
    yield _sse(type="thinking", step="Locating nearest chargers…")
    location_query = _extract_location_query(message)
    coords = await _geocode(location_query, http_client) if location_query else None

    if coords:
        user_lat, user_lng, location_label = coords
        augmented_question = (
            f"{message}\n\n[User location geocoded: {location_label} at "
            f"lat={user_lat}, lng={user_lng}. "
            f"Compute Haversine distance in km from ({user_lat}, {user_lng}) to each lot's "
            f"(latitude, longitude). Return DISTINCT location_name_clean, latitude, longitude, distance_km ORDER BY distance_km ASC.]"
        )
        sql_raw, in_tok, out_tok = await llm.call_deepseek(
            http_client,
            system=SQL_PROMPT.system,
            user=SQL_PROMPT.user.format(
                parquet_path=parquet_path,
                retrieved_context=context,
                user_question=augmented_question,
                data_year=data_year,
                data_year_int=data_year_int,
                data_complete_year=data_complete_year,
            ),
        )
        budget.log_usage("deepseek-v4-flash", in_tok, out_tok)
        sql = _extract_sql(sql_raw)
        result = await asyncio.to_thread(query_engine.run_query, sql, parquet_path)

        if not isinstance(result, str):
            answer, in_tok2, out_tok2 = await llm.call_deepseek(
                http_client,
                system=NEAREST_PROMPT.system,
                user=NEAREST_PROMPT.user.format(
                    user_question=message,
                    user_lat=user_lat,
                    user_lng=user_lng,
                    location_label=location_label,
                    query_results=_format_results(result),
                ),
                history=history or None,
            )
            budget.log_usage("deepseek-v4-flash", in_tok2, out_tok2)
            map_data, map_ts = _extract_map_payload(result)
            yield _sse(
                type="answer", answer=answer, sql=sql,
                chart_html=None, map_data=map_data, map_time_series=map_ts,
                spend=round(budget.get_monthly_spend(), 6),
                warning=budget.is_warning(), data_gap_warning=False,
                context_tokens=in_tok2,
            )
            return

    # fallback: no geocode or SQL failed — answer from RAG context directly
    async for event in _handle_direct(message, http_client, context, history):
        yield event


async def _handle_sql(
    message: str,
    http_client: httpx.AsyncClient,
    context: str,
    parquet_path: str,
    data_year: str,
    data_year_int: int,
    data_complete_year: int,
    gap_warning: bool,
    history: list[dict],
):
    yield _sse(type="thinking", step="Writing SQL query…")
    sql_raw, in_tok, out_tok = await llm.call_deepseek(
        http_client,
        system=SQL_PROMPT.system,
        user=SQL_PROMPT.user.format(
            parquet_path=parquet_path,
            retrieved_context=context,
            user_question=message,
            data_year=data_year,
            data_year_int=data_year_int,
            data_complete_year=data_complete_year,
        ),
        history=history or None,
    )
    budget.log_usage("deepseek-v4-flash", in_tok, out_tok)
    sql = _extract_sql(sql_raw)

    yield _sse(type="thinking", step="Querying dataset…")
    result = await asyncio.to_thread(query_engine.run_query, sql, parquet_path)

    if isinstance(result, str):
        yield _sse(type="thinking", step="Fixing SQL error…")
        fixed_raw, in_tok_f, out_tok_f = await llm.call_deepseek(
            http_client,
            system=SQL_FIX_PROMPT.system,
            user=SQL_FIX_PROMPT.user.format(sql=sql, error=result),
        )
        budget.log_usage("deepseek-v4-flash", in_tok_f, out_tok_f)
        sql = _extract_sql(fixed_raw)
        result = await asyncio.to_thread(query_engine.run_query, sql, parquet_path)

    if isinstance(result, str):
        yield _sse(
            type="answer",
            answer=f"Query error: {result}",
            sql=sql, chart_html=None, map_data=None, map_time_series=None,
            spend=round(budget.get_monthly_spend(), 6),
            warning=budget.is_warning(), data_gap_warning=gap_warning,
            context_tokens=in_tok,
        )
        return

    yield _sse(type="thinking", step="Interpreting results…")
    interpretation, in_tok2, out_tok2 = await llm.call_deepseek(
        http_client,
        system=INTERPRET_PROMPT.system,
        user=INTERPRET_PROMPT.user.format(
            user_question=message,
            sql_query=sql,
            query_results=_format_results(result),
            data_year=data_year,
            data_complete_year=data_complete_year,
        ),
        history=history or None,
    )
    budget.log_usage("deepseek-v4-flash", in_tok2, out_tok2)

    chart_html = None
    chart_code = _extract_code(interpretation)
    if chart_code:
        yield _sse(type="thinking", step="Rendering chart…")
        chart_result = await asyncio.to_thread(executor.run_chart_code, chart_code)
        if chart_result["success"]:
            chart_html = chart_result["chart_html"]

    map_style = _extract_map_style(interpretation)
    map_data, map_ts = _extract_map_payload(result, preferred_metric=map_style.get("metric_col") if map_style else None)
    yield _sse(
        type="answer",
        answer=_strip_code(interpretation),
        sql=sql, chart_html=chart_html, map_data=map_data, map_time_series=map_ts,
        map_style={k: v for k, v in (map_style or {}).items() if k != "metric_col"} or None,
        spend=round(budget.get_monthly_spend(), 6),
        warning=budget.is_warning(), data_gap_warning=gap_warning,
        context_tokens=in_tok2,
    )


async def stream(
    message: str,
    http_client: httpx.AsyncClient,
    chroma_client,
    *,
    parquet_path: str,
    data_year: str,
    data_year_int: int,
    data_complete_year: int,
    history: list[dict] | None = None,
):
    history = history or []
    try:
        gap_warning = _data_gap_warning(message, data_year_int)

        yield _sse(type="thinking", step="Classifying question…")

        if not await guard.is_ev_question(message, http_client, history=history):
            yield _sse(
                type="answer",
                answer="I can only answer questions about NYC EV charging at municipal parking facilities.",
                sql="", chart_html=None, map_data=None,
                spend=0.0, warning=budget.is_warning(), data_gap_warning=False,
                context_tokens=0,
            )
            return

        yield _sse(type="thinking", step="Retrieving context…")
        context = await asyncio.to_thread(rag.retrieve_context, message, chroma_client)
        route = _detect_route(message, history)
        use_reasoner = _needs_reasoning(message, history)

        if route == "direct":
            async for event in _handle_direct(message, http_client, context, history, use_reasoner=use_reasoner):
                yield event
            return

        if route == "nearest":
            async for event in _handle_nearest(
                message, http_client, context,
                parquet_path, data_year, data_year_int, data_complete_year, history,
            ):
                yield event
            return

        if route == "explain":
            prior_sql = _extract_last_sql_from_history(history)
            async for event in _handle_explain(
                message, http_client, prior_sql,
                parquet_path, data_year, data_complete_year, history, gap_warning,
                use_reasoner=use_reasoner,
            ):
                yield event
            return

        async for event in _handle_sql(
            message, http_client, context,
            parquet_path, data_year, data_year_int, data_complete_year, gap_warning, history,
        ):
            yield event

    except Exception as exc:
        yield _sse(type="error", error=str(exc))
