"""
Fake Text Generation WebUI (oobabooga/text-generation-webui) API endpoints.
One of the most popular self-hosted LLM frontends.

Real endpoints:
  GET  /api/v1/model
  POST /api/v1/model        (load/unload model)
  POST /api/v1/generate
  POST /api/v1/chat
  POST /api/v1/token-count
  POST /api/v1/stop-stream
  GET  /api/v1/info

Also exposes an OpenAI-compatible layer under /v1/ — covered by openai_compat.py.
"""

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.fake_responses.generate import _pick_response, Config

router = APIRouter()

_CURRENT_MODEL = "TheBloke/Mistral-7B-Instruct-v0.2-GGUF"


# ── GET /api/v1/model ─────────────────────────────────────────────────────────

@router.get("/api/v1/model")
async def tgw_get_model():
    return JSONResponse(content={
        "result": _CURRENT_MODEL,
        "shared.model_name": _CURRENT_MODEL,
        "shared.lora_names": [],
        "loader": "llama.cpp",
    })


# ── POST /api/v1/model ────────────────────────────────────────────────────────

@router.post("/api/v1/model")
async def tgw_load_model(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    model = body.get("model_name", _CURRENT_MODEL)
    action = body.get("action", "load")
    return JSONResponse(content={
        "result":     "success",
        "model_name": model,
        "action":     action,
    })


# ── GET /api/v1/info ──────────────────────────────────────────────────────────

@router.get("/api/v1/info")
async def tgw_info():
    return JSONResponse(content={
        "version":    "1.11.0",
        "model_name": _CURRENT_MODEL,
        "loader":     "llama.cpp",
        "gpu_memory": {"used": 2048, "total": 8192},
    })


# ── POST /api/v1/generate ─────────────────────────────────────────────────────

@router.post("/api/v1/generate")
async def tgw_generate(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt  = body.get("prompt", "")
    stream  = body.get("stream", False)
    max_new = body.get("max_new_tokens", 200)

    response_text = _pick_response(str(prompt))

    if stream:
        return StreamingResponse(
            _tgw_stream(response_text),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return JSONResponse(content={
        "results": [
            {
                "text":          response_text,
                "token_count":   len(response_text.split()),
                "has_new_text":  True,
                "new_token":     response_text.split()[-1] if response_text else "",
                "finish_reason": "stop",
            }
        ]
    })


async def _tgw_stream(response_text: str):
    words = response_text.split()
    for i, word in enumerate(words):
        is_last = i == len(words) - 1
        data = json.dumps({
            "event":     "text_stream",
            "message_num": i,
            "text":      word + (" " if not is_last else ""),
        })
        yield f"data: {data}\n\n".encode()
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)

    yield b"data: " + json.dumps({"event": "stream_end", "message_num": len(words)}).encode() + b"\n\n"


# ── POST /api/v1/chat ─────────────────────────────────────────────────────────

@router.post("/api/v1/chat")
async def tgw_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_input   = body.get("user_input", "")
    history      = body.get("history", {"internal": [], "visible": []})
    stream       = body.get("stream", False)
    regenerate   = body.get("regenerate", False)

    response_text = _pick_response(str(user_input))

    new_history = {
        "internal": (history.get("internal", []) + [[user_input, response_text]]),
        "visible":  (history.get("visible",  []) + [[user_input, response_text]]),
    }

    if stream:
        return StreamingResponse(
            _tgw_chat_stream(response_text, new_history),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return JSONResponse(content={
        "results": [{"history": new_history}]
    })


async def _tgw_chat_stream(response_text: str, final_history: dict):
    words = response_text.split()
    for i, word in enumerate(words):
        data = json.dumps({
            "event":      "text_stream",
            "message_num": i,
            "history": {
                "internal": [],
                "visible":  [["...", " ".join(words[:i + 1])]],
            },
        })
        yield f"data: {data}\n\n".encode()
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)

    yield b"data: " + json.dumps({
        "event":      "stream_end",
        "message_num": len(words),
        "history":    final_history,
    }).encode() + b"\n\n"


# ── POST /api/v1/token-count ──────────────────────────────────────────────────

@router.post("/api/v1/token-count")
async def tgw_token_count(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    prompt = body.get("prompt", "")
    return JSONResponse(content={"results": [{"tokens": len(str(prompt).split())}]})


# ── POST /api/v1/stop-stream ──────────────────────────────────────────────────

@router.post("/api/v1/stop-stream")
async def tgw_stop_stream():
    return JSONResponse(content={"results": ["Successfully interrupted."]})
