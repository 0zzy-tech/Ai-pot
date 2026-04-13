"""
Fake llama.cpp HTTP server endpoints.
The llama.cpp server is the native C++ inference backend used by many tools.

Real endpoints:
  GET  /health
  GET  /slots
  POST /completion
  POST /tokenize
  POST /detokenize
  POST /embedding
  POST /infill          (fill-in-the-middle for code)
  GET  /props
  POST /v1/chat/completions  (OpenAI compat — handled by openai_compat.py)
  POST /v1/completions       (OpenAI compat)
"""

import asyncio
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.fake_responses.generate import _pick_response, Config
from app.fake_responses.embeddings import fake_embedding

router = APIRouter()


# ── GET /health ───────────────────────────────────────────────────────────────

@router.get("/health")
async def llamacpp_health():
    return JSONResponse(content={"status": "ok"})


# ── GET /props ────────────────────────────────────────────────────────────────

@router.get("/props")
async def llamacpp_props():
    return JSONResponse(content={
        "system_prompt":       "",
        "default_generation_settings": {
            "n_ctx":           4096,
            "n_predict":       -1,
            "model":           "mistral-7b-instruct-v0.3.Q4_K_M.gguf",
            "seed":            -1,
            "temperature":     0.8,
            "dynatemp_range":  0.0,
            "top_k":           40,
            "top_p":           0.95,
            "min_p":           0.05,
            "repeat_penalty":  1.1,
        },
        "total_slots":  1,
        "model_path":   "/models/mistral-7b-instruct-v0.3.Q4_K_M.gguf",
    })


# ── GET /slots ────────────────────────────────────────────────────────────────

@router.get("/slots")
async def llamacpp_slots():
    return JSONResponse(content=[
        {
            "id":              0,
            "state":           0,        # 0 = idle
            "is_processing":   False,
            "prompt":          "",
            "model":           "mistral-7b-instruct-v0.3.Q4_K_M.gguf",
            "n_ctx":           4096,
            "n_predict":       -1,
            "temperature":     0.8,
            "top_k":           40,
            "top_p":           0.95,
            "repeat_penalty":  1.1,
            "n_keep":          0,
            "n_discard":       0,
            "truncated":       False,
            "tokens_predicted":0,
            "tokens_evaluated":0,
        }
    ])


# ── POST /completion ──────────────────────────────────────────────────────────

@router.post("/completion")
async def llamacpp_completion(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt  = body.get("prompt", "")
    stream  = body.get("stream", False)

    response_text = _pick_response(str(prompt))
    tokens = response_text.split()

    if stream:
        return StreamingResponse(
            _llamacpp_stream(response_text),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return JSONResponse(content={
        "content":             response_text,
        "stop":                True,
        "id_slot":             0,
        "model":               "mistral-7b-instruct-v0.3.Q4_K_M.gguf",
        "prompt":              prompt[:100],
        "stop_type":           "eos",
        "stopping_word":       "",
        "tokens_cached":       0,
        "tokens_evaluated":    len(str(prompt).split()),
        "truncated":           False,
        "generation_settings": {
            "n_ctx":        4096,
            "n_predict":    -1,
            "temperature":  0.8,
            "seed":         -1,
        },
        "timings": {
            "prompt_n":          len(str(prompt).split()),
            "prompt_ms":         42.0,
            "prompt_per_token_ms": 2.1,
            "prompt_per_second": 476.0,
            "predicted_n":       len(tokens),
            "predicted_ms":      float(len(tokens) * 40),
            "predicted_per_token_ms": 40.0,
            "predicted_per_second":   25.0,
        },
    })


async def _llamacpp_stream(response_text: str):
    tokens = response_text.split()
    for i, token in enumerate(tokens):
        is_last = i == len(tokens) - 1
        data = json.dumps({
            "content":          token + (" " if not is_last else ""),
            "stop":             is_last,
            "id_slot":          0,
            "model":            "mistral-7b-instruct-v0.3.Q4_K_M.gguf",
            "tokens_predicted": i + 1,
        })
        yield f"data: {data}\n\n".encode()
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)


# ── POST /tokenize ────────────────────────────────────────────────────────────

@router.post("/tokenize")
async def llamacpp_tokenize(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    content = body.get("content", "")
    # Return fake token IDs (word-level approximation)
    words = str(content).split()
    return JSONResponse(content={"tokens": [1000 + i for i in range(len(words))]})


# ── POST /detokenize ──────────────────────────────────────────────────────────

@router.post("/detokenize")
async def llamacpp_detokenize(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    tokens = body.get("tokens", [])
    return JSONResponse(content={"content": f"detokenized text ({len(tokens)} tokens)"})


# ── POST /embedding ───────────────────────────────────────────────────────────

@router.post("/embedding")
async def llamacpp_embedding(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    content = str(body.get("content", ""))
    return JSONResponse(content={
        "embedding": fake_embedding(content, dims=4096),
        "index":     0,
    })


# ── POST /infill (fill-in-the-middle / code completion) ──────────────────────

@router.post("/infill")
async def llamacpp_infill(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    input_prefix = body.get("input_prefix", "")
    input_suffix = body.get("input_suffix", "")
    stream = body.get("stream", False)

    # Fake FIM completion
    response_text = "    # implementation\n    pass\n"

    if stream:
        return StreamingResponse(
            _llamacpp_stream(response_text),
            media_type="text/event-stream",
        )

    return JSONResponse(content={
        "content":   response_text,
        "stop":      True,
        "id_slot":   0,
        "model":     "mistral-7b-instruct-v0.3.Q4_K_M.gguf",
        "stop_type": "eos",
        "timings":   {"predicted_n": 6, "predicted_per_second": 25.0},
    })
