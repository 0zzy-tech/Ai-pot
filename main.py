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
    deception,
    gemini,
    huggingface,
    llamacpp,
    localai_ext,
    lmstudio,
    mistral,
    ollama,
    openai_compat,
    stablediffusion,
    textgenwebui,
    vllm,
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

    # Load custom detection rules into memory
    from app.database import get_custom_rules
    from app.custom_rules import reload_rules
    reload_rules(await get_custom_rules())

    # Start background tasks (threat feed refresh, data retention, scheduled reports)
    from app.scheduler import start_background_tasks
    from app.threatfeeds import threat_feed_task
    asyncio.create_task(threat_feed_task())
    await start_background_tasks()

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
app.include_router(vllm.router)
app.include_router(lmstudio.router)
app.include_router(dashboard.router)
app.include_router(deception.router)
app.include_router(websocket.router)

if Config.METRICS_ENABLED:
    from app.routes import metrics
    app.include_router(metrics.router)


# ── Global capture + service-gate middleware ──────────────────────────────────
# Raw ASGI middleware — avoids BaseHTTPMiddleware entirely.
# BaseHTTPMiddleware (used by @app.middleware("http")) has a known bug in
# Starlette 0.40+ where it calls receive() after a StreamingResponse starts
# sending and raises RuntimeError if it gets http.request instead of
# http.disconnect — breaking CSV exports and any other streaming endpoint.

class _CaptureMiddleware:
    """
    1. Buffers the full request body (needed for logging).
    2. Service-gates disabled services → 404.
    3. Logs every non-internal request asynchronously.
    """
    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # Buffer the full request body from the real ASGI receive
        chunks = []
        more = True
        while more:
            msg = await receive()
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)

        # Stateful replay: downstream handlers get the body once, then disconnect
        _done = False
        async def replay_receive():
            nonlocal _done
            if not _done:
                _done = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        path  = scope.get("path", "")
        client = scope.get("client") or ("unknown", 0)
        client_ip = client[0]

        skip = (
            path.startswith(("/__admin", "/static", "/ws", "/favicon"))
            or client_ip == "127.0.0.1"
        )

        # Allow-list gate — whitelisted IPs pass through without logging
        if not skip and service_registry.is_ip_allowed(client_ip):
            await self._app(scope, replay_receive, send)
            return

        # IP block gate — blocked IPs get 429 immediately (still logged)
        if not skip and service_registry.is_ip_blocked(client_ip):
            req = Request(scope)
            asyncio.create_task(log_request(req, body, 429))
            await send({"type": "http.response.start", "status": 429,
                        "headers": [[b"content-type", b"text/plain"]]})
            await send({"type": "http.response.body", "body": b"Too Many Requests", "more_body": False})
            return

        # Service gate
        if not service_registry.is_path_enabled(path):
            if not skip:
                req = Request(scope)
                asyncio.create_task(log_request(req, body, 404))
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        # Tarpit: delay response to waste attacker time when enabled for this service
        if not skip and service_registry.is_path_tarpitted(path):
            await asyncio.sleep(Config.TARPIT_DELAY_SECS)

        # Capture the response status code for logging
        captured_status = [200]
        async def capturing_send(msg):
            if msg["type"] == "http.response.start":
                captured_status[0] = msg["status"]
            await send(msg)

        try:
            await self._app(scope, replay_receive, capturing_send)
        except Exception:
            logger.exception("Unhandled error in ASGI app for path %s", path)
            raise

        if not skip:
            req = Request(scope)
            asyncio.create_task(log_request(req, body, captured_status[0]))


app.add_middleware(_CaptureMiddleware)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        workers=1,          # Single worker required for SQLite write lock + WebSocket
        log_level="warning",
        access_log=False,   # We do our own logging
    )
