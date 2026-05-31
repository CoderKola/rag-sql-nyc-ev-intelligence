import asyncio
import re

import httpx

from ..infra import budget
from ..services import executor, llm, query_engine
from ..utils.formatting import extract_code, extract_sql, format_results, sse, strip_code
from ..utils.maps import extract_map_payload, extract_map_style
from ..data.prompts import DIRECT_PROMPT, INTERPRET_PROMPT, NEAREST_PROMPT, SQL_FIX_PROMPT, SQL_PROMPT


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


async def handle_direct(
    message: str,
    http_client: httpx.AsyncClient,
    context: str,
    history: list[dict],
    use_reasoner: bool = False,
):
    if use_reasoner:
        yield sse(type="thinking", step="Reasoning through your question…")
        _, answer, in_tok, out_tok = await llm.call_deepseek_reasoner(
            http_client,
            system=DIRECT_PROMPT.system,
            user=DIRECT_PROMPT.user.format(retrieved_context=context, user_question=message),
            history=history or None,
        )
        budget.log_usage("deepseek-reasoner", in_tok, out_tok)
    else:
        yield sse(type="thinking", step="Composing answer…")
        answer, in_tok, out_tok = await llm.call_deepseek(
            http_client,
            system=DIRECT_PROMPT.system,
            user=DIRECT_PROMPT.user.format(retrieved_context=context, user_question=message),
            history=history or None,
        )
        budget.log_usage("deepseek-v4-flash", in_tok, out_tok)
    yield sse(
        type="answer", answer=answer, sql="",
        chart_html=None, map_data=None,
        spend=round(budget.get_monthly_spend(), 6),
        warning=budget.is_warning(), data_gap_warning=False,
        context_tokens=in_tok,
    )


async def handle_nearest(
    message: str,
    http_client: httpx.AsyncClient,
    context: str,
    parquet_path: str,
    data_year: str,
    data_year_int: int,
    data_complete_year: int,
    history: list[dict],
):
    yield sse(type="thinking", step="Locating nearest chargers…")
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
        sql = extract_sql(sql_raw)
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
                    query_results=format_results(result),
                ),
                history=history or None,
            )
            budget.log_usage("deepseek-v4-flash", in_tok2, out_tok2)
            map_data, map_ts = extract_map_payload(result)
            yield sse(
                type="answer", answer=answer, sql=sql,
                chart_html=None, map_data=map_data, map_time_series=map_ts,
                spend=round(budget.get_monthly_spend(), 6),
                warning=budget.is_warning(), data_gap_warning=False,
                context_tokens=in_tok2,
            )
            return

    # fallback: no geocode or SQL failed — answer from RAG context directly
    async for event in handle_direct(message, http_client, context, history):
        yield event


async def handle_explain(
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
    yield sse(type="thinking", step="Re-running prior query…")
    result = await asyncio.to_thread(query_engine.run_query, prior_sql, parquet_path)

    if isinstance(result, str):
        # SQL failed — fall back to answering from history text
        if use_reasoner:
            yield sse(type="thinking", step="Reasoning through your question…")
            _, answer, in_tok, out_tok = await llm.call_deepseek_reasoner(
                http_client,
                system=INTERPRET_PROMPT.system,
                user=f"The user asked: {message}\n\nPlease elaborate based on the prior analysis in the conversation.",
                history=history or None,
            )
            budget.log_usage("deepseek-reasoner", in_tok, out_tok)
        else:
            yield sse(type="thinking", step="Composing answer from prior results…")
            answer, in_tok, out_tok = await llm.call_deepseek(
                http_client,
                system=INTERPRET_PROMPT.system,
                user=f"The user asked: {message}\n\nPlease elaborate based on the prior analysis in the conversation.",
                history=history or None,
            )
            budget.log_usage("deepseek-v4-flash", in_tok, out_tok)
        yield sse(
            type="answer", answer=strip_code(answer), sql=prior_sql,
            chart_html=None, map_data=None,
            spend=round(budget.get_monthly_spend(), 6),
            warning=budget.is_warning(), data_gap_warning=gap_warning,
            context_tokens=in_tok,
        )
        return

    if use_reasoner:
        yield sse(type="thinking", step="Reasoning through results…")
        _, interpretation, in_tok, out_tok = await llm.call_deepseek_reasoner(
            http_client,
            system=INTERPRET_PROMPT.system,
            user=INTERPRET_PROMPT.user.format(
                user_question=message,
                sql_query=prior_sql,
                query_results=format_results(result),
                data_year=data_year,
                data_complete_year=data_complete_year,
            ),
            history=history or None,
        )
        budget.log_usage("deepseek-reasoner", in_tok, out_tok)
    else:
        yield sse(type="thinking", step="Interpreting results…")
        interpretation, in_tok, out_tok = await llm.call_deepseek(
            http_client,
            system=INTERPRET_PROMPT.system,
            user=INTERPRET_PROMPT.user.format(
                user_question=message,
                sql_query=prior_sql,
                query_results=format_results(result),
                data_year=data_year,
                data_complete_year=data_complete_year,
            ),
            history=history or None,
        )
        budget.log_usage("deepseek-v4-flash", in_tok, out_tok)

    chart_html = None
    chart_code = extract_code(interpretation)
    if chart_code:
        yield sse(type="thinking", step="Rendering chart…")
        chart_result = await asyncio.to_thread(executor.run_chart_code, chart_code)
        if chart_result["success"]:
            chart_html = chart_result["chart_html"]

    map_style = extract_map_style(interpretation)
    map_data, map_ts = extract_map_payload(
        result, preferred_metric=map_style.get("metric_col") if map_style else None
    )
    yield sse(
        type="answer", answer=strip_code(interpretation), sql=prior_sql,
        chart_html=chart_html, map_data=map_data, map_time_series=map_ts,
        map_style={k: v for k, v in (map_style or {}).items() if k != "metric_col"} or None,
        spend=round(budget.get_monthly_spend(), 6),
        warning=budget.is_warning(), data_gap_warning=gap_warning,
        context_tokens=in_tok,
    )


async def handle_sql(
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
    yield sse(type="thinking", step="Writing SQL query…")
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
    sql = extract_sql(sql_raw)

    yield sse(type="thinking", step="Querying dataset…")
    result = await asyncio.to_thread(query_engine.run_query, sql, parquet_path)

    if isinstance(result, str):
        yield sse(type="thinking", step="Fixing SQL error…")
        fixed_raw, in_tok_f, out_tok_f = await llm.call_deepseek(
            http_client,
            system=SQL_FIX_PROMPT.system,
            user=SQL_FIX_PROMPT.user.format(sql=sql, error=result),
        )
        budget.log_usage("deepseek-v4-flash", in_tok_f, out_tok_f)
        sql = extract_sql(fixed_raw)
        result = await asyncio.to_thread(query_engine.run_query, sql, parquet_path)

    if isinstance(result, str):
        yield sse(
            type="answer",
            answer=f"Query error: {result}",
            sql=sql, chart_html=None, map_data=None, map_time_series=None,
            spend=round(budget.get_monthly_spend(), 6),
            warning=budget.is_warning(), data_gap_warning=gap_warning,
            context_tokens=in_tok,
        )
        return

    yield sse(type="thinking", step="Interpreting results…")
    interpretation, in_tok2, out_tok2 = await llm.call_deepseek(
        http_client,
        system=INTERPRET_PROMPT.system,
        user=INTERPRET_PROMPT.user.format(
            user_question=message,
            sql_query=sql,
            query_results=format_results(result),
            data_year=data_year,
            data_complete_year=data_complete_year,
        ),
        history=history or None,
    )
    budget.log_usage("deepseek-v4-flash", in_tok2, out_tok2)

    chart_html = None
    chart_code = extract_code(interpretation)
    if chart_code:
        yield sse(type="thinking", step="Rendering chart…")
        chart_result = await asyncio.to_thread(executor.run_chart_code, chart_code)
        if chart_result["success"]:
            chart_html = chart_result["chart_html"]

    map_style = extract_map_style(interpretation)
    map_data, map_ts = extract_map_payload(
        result, preferred_metric=map_style.get("metric_col") if map_style else None
    )
    yield sse(
        type="answer",
        answer=strip_code(interpretation),
        sql=sql, chart_html=chart_html, map_data=map_data, map_time_series=map_ts,
        map_style={k: v for k, v in (map_style or {}).items() if k != "metric_col"} or None,
        spend=round(budget.get_monthly_spend(), 6),
        warning=budget.is_warning(), data_gap_warning=gap_warning,
        context_tokens=in_tok2,
    )
