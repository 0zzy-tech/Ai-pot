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
  1. Forwarded to the matching fake-response handler
  2. Logged asynchronously (classify + geolocate + SQLite + WebSocket broadcast)

Dashboard at /__admin (HTTP Basic Auth).
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.logger import log_request
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
    logger.info(
        "AI Honeypot running on %s:%d  |  Dashboard: http://localhost:%d/__admin\n"
        "  Simulating: Ollama · Anthropic · HuggingFace TGI · llama.cpp · "
        "Text-Gen-WebUI · Cohere · Mistral · Gemini · SD-WebUI · ComfyUI · LocalAI",
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

# ── Routers ────────────────────────────────────────────────────────────────────
# Order matters: more specific routes first to avoid prefix conflicts.

# Ollama native API (port 11434 default)
app.include_router(ollama.router)

# OpenAI-compatible layer (/v1/*)  — shared by Ollama, LocalAI, vLLM, LM Studio…
app.include_router(openai_compat.router)

# Anthropic Claude API (/v1/messages, /v1/complete)
app.include_router(anthropic.router)

# HuggingFace TGI (/generate, /generate_stream, /info, /metrics…)
app.include_router(huggingface.router)

# llama.cpp HTTP server (/completion, /embedding, /slots, /infill…)
app.include_router(llamacpp.router)

# Text Generation WebUI / oobabooga (/api/v1/*)
app.include_router(textgenwebui.router)

# Cohere API (/v1/chat, /v1/generate, /v1/embed, /v1/rerank…)
app.include_router(cohere.router)

# Mistral AI (/v1/fim/completions, /v1/agents…)
app.include_router(mistral.router)

# Google Gemini / Vertex AI (/v1beta/models/*, /v1/models/*)
app.include_router(gemini.router)

# Stable Diffusion WebUI (/sdapi/v1/*, /info)
app.include_router(stablediffusion.router)

# ComfyUI (/prompt, /system_stats, /queue, /history, /view…)
app.include_router(comfyui.router)

# LocalAI extensions beyond /v1/ (audio, image gen, TTS, backends)
app.include_router(localai_ext.router)

# Dashboard and WebSocket
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
