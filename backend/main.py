import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: load ChromaDB client, sentence-transformers model
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/chat")
async def chat(request: Request):
    """Main chat endpoint — full pipeline not yet implemented."""
    raise NotImplementedError


@app.get("/api/status")
async def status():
    """Return current spend, cap, and data freshness."""
    raise NotImplementedError


# Serve SvelteKit static build in prod
if os.getenv("ENV") == "production":
    app.mount("/", StaticFiles(directory="build", html=True), name="static")
