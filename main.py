"""
AI Honeypot — main entry point.

Masquerades as multiple AI API servers simultaneously on port 11434.
Simulated platforms:
  - Ollama (native + OpenAI-compatible)
  - Anthropic Claude API
  - HuggingFace Text Generation Inference (TGI)
  - llama.cpp HTTP server
  - Text Generation WebUI (oobabooga)
  - Cohere API
  - Mistral AI API
  - Google Gemini / Generative AI API
  - Stable Diffusion WebUI (Automatic1111 / FORGE)
  - ComfyUI
  - LocalAI (audio, image generation extensions)

Every incoming request is:
  1. Service-gate checked (disabled services return 404 but are still logged)
  2. Forwarded to the matching fake-response handler
  3. Logged asynchronously (classify + geolocate + SQLite + WebSocket broadcast)

Dashboard at /__admin (HTTP Basic Auth).
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.logger import log_request
from app import service_registry
from app.routes import (
    anthropic,
    comfyui,
    cohere,
    dashboard,
    gemini,
    huggingface,
    llamacpp,
    localai_ext,
    mistral,
    ollama,
    openai_compat,
    stablediffusion,
    textgenwebui,
    websocket,
)
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
    await service_registry.init_service_registry()
    logger.info(
        "AI Honeypot running on %s:%d  |  Dashboard: http://localhost:%d%s\n"
        "  Simulating: Ollama · Anthropic · HuggingFace TGI · llama.cpp · "
        "Text-Gen-WebUI · Cohere · Mistral · Gemini · SD-WebUI · ComfyUI · LocalAI",
        Config.HOST,
        Config.PORT,
        Config.PORT,
        Config.ADMIN_PREFIX,
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

# ── Routers ────────────────────────────────────────────────────────────────────
# Order matters: more specific routes first to avoid prefix conflicts.

app.include_router(ollama.router)
app.include_router(openai_compat.router)
app.include_router(anthropic.router)
app.include_router(huggingface.router)
app.include_router(llamacpp.router)
app.include_router(textgenwebui.router)
app.include_router(cohere.router)
app.include_router(mistral.router)
app.include_router(gemini.router)
app.include_router(stablediffusion.router)
app.include_router(comfyui.router)
app.include_router(localai_ext.router)
app.include_router(dashboard.router)
app.include_router(websocket.router)


# ── Global capture + service-gate middleware ──────────────────────────────────
@app.middleware("http")
async def capture_all_requests(request: Request, call_next):
    """
    1. Reads the request body (needed for logging).
    2. Checks whether the targeted service is enabled.
       - If disabled: logs the attempt as status 503 and returns 404.
       - If enabled: forwards to the handler normally.
    3. Logs every request asynchronously (never delays the response).
    """
    body = await request.body()

    # Re-inject body so downstream handlers can read it.
    # Must be stateful: return http.request once, then http.disconnect.
    # BaseHTTPMiddleware calls receive() again after a StreamingResponse
    # starts and expects http.disconnect — always returning http.request
    # raises a RuntimeError inside Starlette.
    _consumed = False

    async def receive():
        nonlocal _consumed
        if not _consumed:
            _consumed = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    request._receive = receive  # type: ignore[attr-defined]

    path = request.url.path
    client_ip = request.client.host if request.client else ""

    # ── Skip logging for internal/dashboard/healthcheck traffic ───────────
    _skip = (
        path.startswith(("/__admin", "/static", "/ws", "/favicon"))
        or client_ip == "127.0.0.1"
    )

    # ── Service gate ───────────────────────────────────────────────────────
    if not service_registry.is_path_enabled(path):
        # Log the blocked attempt then return 404 (attacker sees nothing there)
        if not _skip:
            asyncio.create_task(log_request(request, body, 404))
        return Response(status_code=404)

    response = await call_next(request)

    # Fire-and-forget logging
    if not _skip:
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
