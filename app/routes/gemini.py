"""
Fake Google Gemini / Generative AI API endpoints.
Captures tools using the Google generativeai SDK or direct REST calls.

Real endpoints (Gemini REST API):
  GET  /v1beta/models
  GET  /v1beta/models/{model}
  POST /v1beta/models/{model}:generateContent
  POST /v1beta/models/{model}:streamGenerateContent
  POST /v1beta/models/{model}:embedContent
  POST /v1beta/models/{model}:batchEmbedContents
  POST /v1beta/models/{model}:countTokens

Also mirrors the /v1/ prefix used by Vertex AI.
"""

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.fake_responses.generate import _pick_response, Config
from app.fake_responses.embeddings import fake_embedding

router = APIRouter()

_GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.0-pro",
    "embedding-001",
    "text-embedding-004",
]


def _model_obj(name: str) -> dict:
    return {
        "name":                  f"models/{name}",
        "version":               "001",
        "displayName":           name.replace("-", " ").title(),
        "description":           f"Google {name.replace('-', ' ').title()} model",
        "inputTokenLimit":       1048576,
        "outputTokenLimit":      8192,
        "supportedGenerationMethods": ["generateContent", "countTokens"],
        "temperature":           1.0,
        "maxTemperature":        2.0,
        "topP":                  0.95,
        "topK":                  64,
    }


def _extract_gemini_text(body: dict) -> str:
    """Extract the user's prompt from Gemini's content format."""
    contents = body.get("contents", [])
    for content in reversed(contents):
        if content.get("role") in ("user", None):
            parts = content.get("parts", [])
            text = " ".join(p.get("text", "") for p in parts if "text" in p)
            if text:
                return text
    return ""


def _gemini_response(model: str, response_text: str) -> dict:
    words = response_text.split()
    return {
        "candidates": [
            {
                "content": {
                    "parts":  [{"text": response_text}],
                    "role":   "model",
                },
                "finishReason":   "STOP",
                "index":          0,
                "safetyRatings": [
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH",        "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_HARASSMENT",         "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",  "probability": "NEGLIGIBLE"},
                ],
            }
        ],
        "usageMetadata": {
            "promptTokenCount":     10,
            "candidatesTokenCount": len(words),
            "totalTokenCount":      10 + len(words),
        },
        "modelVersion": model,
    }


# ── GET /v1beta/models ────────────────────────────────────────────────────────

@router.get("/v1beta/models")
@router.get("/v1/models")
async def gemini_list_models():
    return JSONResponse(content={
        "models": [_model_obj(m) for m in _GEMINI_MODELS]
    })


# ── GET /v1beta/models/{model} ─────────────────────────────────────────────────

@router.get("/v1beta/models/{model:path}")
@router.get("/v1/models/{model:path}")
async def gemini_get_model(model: str):
    # Strip "models/" prefix if present
    model = model.removeprefix("models/")
    return JSONResponse(content=_model_obj(model))


# ── POST /v1beta/models/{model}:generateContent ────────────────────────────────

@router.post("/v1beta/models/{model:path}:generateContent")
@router.post("/v1/models/{model:path}:generateContent")
async def gemini_generate_content(model: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    model = model.removeprefix("models/")
    prompt = _extract_gemini_text(body)
    response_text = _pick_response(prompt)
    return JSONResponse(content=_gemini_response(model, response_text))


# ── POST /v1beta/models/{model}:streamGenerateContent ──────────────────────────

@router.post("/v1beta/models/{model:path}:streamGenerateContent")
@router.post("/v1/models/{model:path}:streamGenerateContent")
async def gemini_stream_generate(model: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    model  = model.removeprefix("models/")
    prompt = _extract_gemini_text(body)
    response_text = _pick_response(prompt)

    return StreamingResponse(
        _gemini_stream(model, response_text),
        media_type="application/json",
        headers={"Transfer-Encoding": "chunked"},
    )


async def _gemini_stream(model: str, response_text: str):
    words = response_text.split()
    yield b"["
    for i, word in enumerate(words):
        chunk = {
            "candidates": [
                {
                    "content": {"parts": [{"text": word + " "}], "role": "model"},
                    "finishReason": "STOP" if i == len(words) - 1 else None,
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount":     10,
                "candidatesTokenCount": i + 1,
                "totalTokenCount":      10 + i + 1,
            },
        }
        if i > 0:
            yield b","
        yield json.dumps(chunk).encode()
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)
    yield b"]"


# ── POST /v1beta/models/{model}:embedContent ──────────────────────────────────

@router.post("/v1beta/models/{model:path}:embedContent")
@router.post("/v1/models/{model:path}:embedContent")
async def gemini_embed(model: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    content = body.get("content", {})
    parts   = content.get("parts", []) if isinstance(content, dict) else []
    text    = " ".join(p.get("text", "") for p in parts if "text" in p)

    return JSONResponse(content={
        "embedding": {
            "values": fake_embedding(text, dims=768),
        }
    })


# ── POST /v1beta/models/{model}:batchEmbedContents ────────────────────────────

@router.post("/v1beta/models/{model:path}:batchEmbedContents")
async def gemini_batch_embed(model: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    requests_list = body.get("requests", [])
    embeddings = []
    for req in requests_list:
        content = req.get("content", {})
        parts   = content.get("parts", []) if isinstance(content, dict) else []
        text    = " ".join(p.get("text", "") for p in parts if "text" in p)
        embeddings.append({"values": fake_embedding(text, dims=768)})

    return JSONResponse(content={"embeddings": embeddings})


# ── POST /v1beta/models/{model}:countTokens ───────────────────────────────────

@router.post("/v1beta/models/{model:path}:countTokens")
async def gemini_count_tokens(model: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    contents = body.get("contents", [])
    total = sum(
        len(" ".join(p.get("text", "") for p in c.get("parts", []) if "text" in p).split())
        for c in contents
    )
    return JSONResponse(content={"totalTokens": total})
