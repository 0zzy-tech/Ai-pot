"""
AI Honeypot — main entry point.

Masquerades as a real Ollama server on port 11434.
Every incoming request is:
  1. Forwarded to the appropriate fake-response handler
  2. Logged asynchronously (classify + geolocate + SQLite + WebSocket broadcast)

Dashboard is at /__admin (HTTP Basic Auth required).
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.logger import log_request
from app.routes import dashboard, ollama, openai_compat, websocket
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising database…")
    await init_db()
    logger.info(
        "AI Honeypot running on %s:%d  |  Dashboard: http://localhost:%d/__admin",
        Config.HOST,
        Config.PORT,
        Config.PORT,
    )
    yield
    logger.info("Shutting down.")


# Disable /docs and /redoc so scanners can't identify this as FastAPI
app = FastAPI(
    title="Ollama",
    version="0.3.12",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# Static files (dashboard assets)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ollama.router)
app.include_router(openai_compat.router)
app.include_router(dashboard.router)
app.include_router(websocket.router)


# ── Global capture middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def capture_all_requests(request: Request, call_next):
    """
    Captures EVERY request (including unknown paths → 404s) for logging.
    Logging is a background task so it never delays the response.
    """
    body = await request.body()

    # Re-inject body so downstream handlers can read it
    async def receive():
        return {"type": "http.request", "body": body}

    request._receive = receive  # type: ignore[attr-defined]

    response = await call_next(request)

    # Fire-and-forget: log asynchronously
    asyncio.create_task(log_request(request, body, response.status_code))

    return response


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        workers=1,          # Single worker required for SQLite write lock + WebSocket
        log_level="warning",
        access_log=False,   # We do our own logging
    )
