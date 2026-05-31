import asyncio

import httpx

from ..infra import budget
from ..services import guard, rag
from ..utils.formatting import sse
from . import handlers
from .router import data_gap_warning, detect_route, extract_last_sql_from_history, needs_reasoning


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
        gap_warning = data_gap_warning(message, data_year_int)

        yield sse(type="thinking", step="Classifying question…")

        if not await guard.is_ev_question(message, http_client, history=history):
            yield sse(
                type="answer",
                answer="I can only answer questions about NYC EV charging at municipal parking facilities.",
                sql="", chart_html=None, map_data=None,
                spend=0.0, warning=budget.is_warning(), data_gap_warning=False,
                context_tokens=0,
            )
            return

        yield sse(type="thinking", step="Retrieving context…")
        context = await asyncio.to_thread(rag.retrieve_context, message, chroma_client)
        route = detect_route(message, history)
        use_reasoner = needs_reasoning(message, history)

        if route == "direct":
            async for event in handlers.handle_direct(message, http_client, context, history, use_reasoner=use_reasoner):
                yield event
            return

        if route == "nearest":
            async for event in handlers.handle_nearest(
                message, http_client, context,
                parquet_path, data_year, data_year_int, data_complete_year, history,
            ):
                yield event
            return

        if route == "explain":
            prior_sql = extract_last_sql_from_history(history)
            async for event in handlers.handle_explain(
                message, http_client, prior_sql,
                parquet_path, data_year, data_complete_year, history, gap_warning,
                use_reasoner=use_reasoner,
            ):
                yield event
            return

        async for event in handlers.handle_sql(
            message, http_client, context,
            parquet_path, data_year, data_year_int, data_complete_year, gap_warning, history,
        ):
            yield event

    except Exception as exc:
        yield sse(type="error", error=str(exc))
