"""
Fake LocalAI extension endpoints — the parts NOT covered by OpenAI-compat.
LocalAI is a drop-in replacement for OpenAI with local model support,
and adds audio, image generation, and TTS endpoints.

Real additional endpoints:
  POST /v1/audio/transcriptions   (Whisper-compatible)
  POST /v1/audio/translations
  POST /tts                       (Text-to-speech, LocalAI native)
  GET  /v1/audio/speech           (OpenAI TTS)
  POST /v1/audio/speech
  POST /v1/images/generations     (Stable Diffusion)
  POST /v1/images/edits
  POST /v1/images/variations
  GET  /readyz                    (health)
  GET  /healthz
  GET  /v1/backends               (LocalAI-specific: list loaded backends)
  GET  /v1/backend/monitor
  POST /v1/backend/shutdown
"""

import base64
import uuid
import time

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response

router = APIRouter()

# Fake 1×1 PNG base64
_FAKE_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
)

# Fake 1-second silent WAV (44 bytes — the smallest valid WAV)
_FAKE_WAV = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"@\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/readyz")
@router.get("/healthz")
async def localai_health():
    return JSONResponse(content={"status": "ok"})


# ── Backends (LocalAI-specific) ───────────────────────────────────────────────

@router.get("/v1/backends")
async def localai_backends():
    return JSONResponse(content={
        "backends": [
            {"name": "llama-cpp",     "type": "llm",   "models": ["mistral-7b-instruct-v0.3"]},
            {"name": "whisper",       "type": "audio",  "models": ["whisper-1"]},
            {"name": "stable-diffusion", "type": "image", "models": ["dall-e-2"]},
            {"name": "bark",          "type": "tts",    "models": ["tts-1"]},
        ]
    })


@router.get("/v1/backend/monitor")
async def localai_backend_monitor():
    return JSONResponse(content={
        "backends": [
            {"name": "llama-cpp",  "status": "running", "memory_usage_mb": 3200},
            {"name": "whisper",    "status": "idle",     "memory_usage_mb": 800},
            {"name": "stable-diffusion", "status": "idle", "memory_usage_mb": 4096},
        ]
    })


@router.post("/v1/backend/shutdown")
async def localai_backend_shutdown(request: Request):
    return JSONResponse(content={"status": "ok"})


# ── Audio transcription (Whisper-compatible) ───────────────────────────────────

@router.post("/v1/audio/transcriptions")
async def localai_transcribe(request: Request):
    # Accept multipart or JSON
    return JSONResponse(content={
        "text": "This is a transcription of the provided audio file.",
        "language": "english",
        "duration": 3.5,
        "segments": [
            {"id": 0, "start": 0.0, "end": 3.5,
             "text": " This is a transcription of the provided audio file.",
             "no_speech_prob": 0.02}
        ],
    })


@router.post("/v1/audio/translations")
async def localai_translate(request: Request):
    return JSONResponse(content={
        "text": "This is the translated text from the provided audio."
    })


# ── Text-to-speech ─────────────────────────────────────────────────────────────

@router.post("/tts")
async def localai_tts(request: Request):
    """LocalAI native TTS endpoint."""
    return Response(
        content=_FAKE_WAV,
        media_type="audio/wav",
        headers={"Content-Disposition": 'attachment; filename="speech.wav"'},
    )


@router.post("/v1/audio/speech")
@router.get("/v1/audio/speech")
async def openai_tts(request: Request):
    """OpenAI-compatible TTS endpoint."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    # Return silent WAV regardless of voice/model
    return Response(
        content=_FAKE_WAV,
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'attachment; filename="speech.mp3"'},
    )


# ── Image generation ───────────────────────────────────────────────────────────

@router.post("/v1/images/generations")
async def localai_image_gen(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt = body.get("prompt", "")
    n      = body.get("n", 1)
    size   = body.get("size", "1024x1024")
    resp_fmt = body.get("response_format", "b64_json")

    images = []
    for _ in range(max(1, n)):
        if resp_fmt == "url":
            images.append({"url": "http://localhost/fake-image.png", "revised_prompt": prompt})
        else:
            images.append({"b64_json": _FAKE_IMAGE_B64, "revised_prompt": prompt})

    return JSONResponse(content={
        "created": int(time.time()),
        "data":    images,
    })


@router.post("/v1/images/edits")
async def localai_image_edit(request: Request):
    return JSONResponse(content={
        "created": int(time.time()),
        "data":    [{"b64_json": _FAKE_IMAGE_B64}],
    })


@router.post("/v1/images/variations")
async def localai_image_variation(request: Request):
    return JSONResponse(content={
        "created": int(time.time()),
        "data":    [{"b64_json": _FAKE_IMAGE_B64}],
    })
