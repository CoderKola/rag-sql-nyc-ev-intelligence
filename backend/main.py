import os
import re
from contextlib import asynccontextmanager

import chromadb
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import budget, pipeline, rate_limit

load_dotenv()

PARQUET_PATH = os.path.abspath(os.getenv("PARQUET_PATH", "./data/parquet/nyc_ev_charging.parquet"))
CHROMA_PATH = os.getenv("CHROMA_PERSIST_PATH", "./data/chroma")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "500"))
CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW", "131072"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "10"))  # last N user+assistant pairs
DATA_YEAR = os.getenv("DATA_THROUGH_YEAR", "May 2026")
_year_match = re.search(r"\d{4}", DATA_YEAR)
DATA_YEAR_INT = int(_year_match.group()) if _year_match else 2024
_month_names = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec",
                "january","february","march","april","june","july","august","september","october","november","december"]
_is_partial_year = any(m in DATA_YEAR.lower() for m in _month_names)
DATA_COMPLETE_YEAR = DATA_YEAR_INT - 1 if _is_partial_year else DATA_YEAR_INT


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    app.state.http_client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        timeout=60.0,
    )
    yield
    await app.state.http_client.aclose()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{p}" for p in range(5173, 5200)],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize_history(raw: list) -> list[dict]:
    """Validate and trim conversation history from the client."""
    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        cleaned.append({"role": role, "content": content[:2000]})
    # keep last MAX_HISTORY_TURNS pairs (each pair = 2 messages)
    max_msgs = MAX_HISTORY_TURNS * 2
    return cleaned[-max_msgs:]


@app.post("/api/chat/stream")
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


@app.get("/api/status")
async def status():
    return JSONResponse({
        "spend": round(budget.get_monthly_spend(), 6),
        "cap": budget.BUDGET_CAP,
        "warning": budget.is_warning(),
        "data_through": DATA_YEAR,
        "context_window": CONTEXT_WINDOW,
        "max_history_turns": MAX_HISTORY_TURNS,
    })
