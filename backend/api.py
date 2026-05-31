from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import pipeline
from .infra import budget, rate_limit
from .config import (
    CONTEXT_WINDOW,
    DATA_COMPLETE_YEAR,
    DATA_YEAR,
    DATA_YEAR_INT,
    MAX_HISTORY_TURNS,
    MAX_INPUT_CHARS,
    PARQUET_PATH,
)

router = APIRouter()


def _sanitize_history(raw: list) -> list[dict]:
    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        cleaned.append({"role": role, "content": content[:2000]})
    max_msgs = MAX_HISTORY_TURNS * 2
    return cleaned[-max_msgs:]


@router.post("/api/chat/stream")
async def chat_stream(request: Request):
    body = await request.json()
    message = str(body.get("message", "")).strip()[:MAX_INPUT_CHARS]

    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)

    ip = (request.client.host or "unknown") if request.client else "unknown"

    if rate_limit.is_rate_limited(ip):
        return JSONResponse({"error": "Rate limit exceeded. Try again in an hour."}, status_code=429)

    if budget.is_over_cap():
        return JSONResponse({"error": "Monthly demo budget exhausted."}, status_code=402)

    rate_limit.record_request(ip)

    history = _sanitize_history(body.get("history", []))

    return StreamingResponse(
        pipeline.stream(
            message,
            request.app.state.http_client,
            request.app.state.chroma_client,
            parquet_path=PARQUET_PATH,
            data_year=DATA_YEAR,
            data_year_int=DATA_YEAR_INT,
            data_complete_year=DATA_COMPLETE_YEAR,
            history=history,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/status")
async def status():
    return JSONResponse({
        "spend": round(budget.get_monthly_spend(), 6),
        "cap": budget.BUDGET_CAP,
        "warning": budget.is_warning(),
        "data_through": DATA_YEAR,
        "context_window": CONTEXT_WINDOW,
        "max_history_turns": MAX_HISTORY_TURNS,
    })
