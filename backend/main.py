from contextlib import asynccontextmanager

import chromadb
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import api
from .config import CHROMA_PATH, DEEPSEEK_API_KEY


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

app.include_router(api.router)
