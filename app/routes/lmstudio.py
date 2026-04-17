"""
LM Studio native API endpoints (/api/v0/).

LM Studio exposes two APIs:
  - OpenAI-compatible /v1/ layer (handled by openai_compat.py)
  - Native /api/v0/ API introduced in LM Studio 0.3+

This file handles the /api/v0/ routes which are unique to LM Studio.
Port: 1234 (default LM Studio)
"""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.fake_responses.models_catalog import FAKE_MODELS

router = APIRouter(prefix="/api/v0")

_FAKE_LMS_MODELS = [
    {
        "id":           m["name"],
        "object":       "model",
        "type":         "llm",
        "publisher":    "lmstudio-community",
        "arch":         "llama",
        "compatibility_type": "gguf",
        "quantization": "Q4_K_M",
        "state":        "loaded" if i == 0 else "not-loaded",
        "max_context_length": 131072,
    }
    for i, m in enumerate(FAKE_MODELS[:4])
]


@router.get("/models")
async def list_models():
    return JSONResponse({"data": _FAKE_LMS_MODELS, "object": "list"})


@router.get("/models/{model_id:path}")
async def get_model(model_id: str):
    for m in _FAKE_LMS_MODELS:
        if m["id"] == model_id:
            return JSONResponse(m)
    return JSONResponse({"error": {"message": f"Model '{model_id}' not found", "code": "model_not_found"}}, status_code=404)


@router.get("/system")
async def system_info():
    return JSONResponse({
        "os":           "linux",
        "arch":         "x64",
        "version":      "0.3.6",
        "build":        "250101",
        "cpu":          {"model": "Intel Core i9", "cores": 16},
        "memory":       {"total": 68719476736, "available": 34359738368},
        "gpu":          [{"name": "NVIDIA GeForce RTX 4090", "vram": 25769803776}],
    })


@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    model = body.get("model", "llama3.2")
    return JSONResponse({
        "id":      f"chatcmpl-lms-{int(time.time())}",
        "object":  "chat.completion",
        "created": int(time.time()),
        "model":   model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "I'm a helpful AI assistant running locally."},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 12, "completion_tokens": 14, "total_tokens": 26},
        "stats": {"tokens_per_second": 42.3, "time_to_first_token": 0.08},
    })


@router.post("/completions")
async def completions(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    model = body.get("model", "llama3.2")
    return JSONResponse({
        "id":      f"cmpl-lms-{int(time.time())}",
        "object":  "text_completion",
        "created": int(time.time()),
        "model":   model,
        "choices": [{"text": " a helpful AI assistant.", "index": 0, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
    })


@router.post("/embeddings")
async def embeddings(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    inputs = body.get("input", [""])
    if isinstance(inputs, str):
        inputs = [inputs]
    return JSONResponse({
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": [0.0] * 768}
            for i in range(len(inputs))
        ],
        "model": body.get("model", "text-embedding-nomic-embed-text-v1.5"),
        "usage": {"prompt_tokens": sum(len(s.split()) for s in inputs), "total_tokens": sum(len(s.split()) for s in inputs)},
    })
