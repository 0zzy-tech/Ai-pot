"""
Fake HuggingFace Text Generation Inference (TGI) server endpoints.
TGI is widely used for self-hosted Hugging Face models.

Real endpoints (TGI v2):
  GET  /
  GET  /health
  GET  /info
  GET  /metrics           (Prometheus format)
  POST /generate          (single request)
  POST /generate_stream   (streaming SSE)
  POST /tokenize
  POST /decode
  GET  /v1/models         (OpenAI-compat, handled by openai_compat.py)
  POST /v1/chat/completions (OpenAI-compat)
"""

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from app.fake_responses.generate import _pick_response, Config

router = APIRouter()

_TGI_MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"


# ── Health / info ─────────────────────────────────────────────────────────────

@router.get("/health")
async def tgi_health():
    return PlainTextResponse("", status_code=200)


@router.get("/info")
async def tgi_info():
    return JSONResponse(content={
        "model_id":           _TGI_MODEL_ID,
        "model_sha":          "e0bc86c23ce5aae8b4b6e9e979f30f003748b04e",
        "model_dtype":        "torch.bfloat16",
        "model_device_type":  "cuda",
        "model_pipeline_tag": "text-generation",
        "max_concurrent_requests": 128,
        "max_best_of":        2,
        "max_stop_sequences": 4,
        "max_input_length":   4096,
        "max_total_tokens":   8192,
        "waiting_served_ratio": 1.2,
        "max_batch_prefill_tokens": 4096,
        "max_batch_total_tokens": 16384,
        "validation_workers": 2,
        "version":            "2.0.4",
        "sha":                "a9a13f3a33c87bc00a2e7f2eba5db3a9c03f0bb9",
        "docker_label":       "sha-a9a13f3",
    })


# ── Metrics (Prometheus format) ───────────────────────────────────────────────

@router.get("/metrics")
async def tgi_metrics():
    metrics = """# HELP tgi_request_count Total number of requests
# TYPE tgi_request_count counter
tgi_request_count{method="generate"} 4721.0
tgi_request_count{method="generate_stream"} 18234.0
# HELP tgi_request_duration_seconds Request duration
# TYPE tgi_request_duration_seconds histogram
tgi_request_duration_seconds_bucket{le="0.005"} 142.0
tgi_request_duration_seconds_bucket{le="0.05"} 983.0
tgi_request_duration_seconds_bucket{le="0.5"} 4120.0
tgi_request_duration_seconds_bucket{le="+Inf"} 4721.0
# HELP tgi_queue_size Current queue size
# TYPE tgi_queue_size gauge
tgi_queue_size 0.0
# HELP tgi_batch_size Current batch size
# TYPE tgi_batch_size gauge
tgi_batch_size 1.0
"""
    return PlainTextResponse(metrics, media_type="text/plain; version=0.0.4")


# ── POST /generate ─────────────────────────────────────────────────────────────

@router.post("/generate")
async def tgi_generate(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt  = body.get("inputs", body.get("prompt", ""))
    params  = body.get("parameters", {})
    max_tok = params.get("max_new_tokens", 256)

    response_text = _pick_response(str(prompt))
    tokens = response_text.split()

    return JSONResponse(content={
        "generated_text": response_text,
        "details": {
            "finish_reason":    "eos_token",
            "generated_tokens": len(tokens),
            "seed":             None,
            "prefill": [
                {"id": i, "text": t, "logprob": -0.5}
                for i, t in enumerate(str(prompt).split()[:5])
            ],
            "tokens": [
                {"id": 1000 + i, "text": t, "logprob": -0.5, "special": False}
                for i, t in enumerate(tokens[:10])
            ],
        },
    })


# ── POST /generate_stream ──────────────────────────────────────────────────────

@router.post("/generate_stream")
async def tgi_generate_stream(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt = body.get("inputs", body.get("prompt", ""))
    response_text = _pick_response(str(prompt))

    return StreamingResponse(
        _tgi_stream(response_text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _tgi_stream(response_text: str):
    tokens = response_text.split()
    for i, token in enumerate(tokens):
        is_last = i == len(tokens) - 1
        data = {
            "token": {
                "id":      1000 + i,
                "text":    token + (" " if not is_last else ""),
                "logprob": -0.42,
                "special": False,
            },
            "generated_text": response_text if is_last else None,
            "details": {
                "finish_reason":    "eos_token",
                "generated_tokens": len(tokens),
                "seed":             None,
            } if is_last else None,
        }
        yield f"data:{json.dumps(data)}\n\n".encode()
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)


# ── POST /tokenize ─────────────────────────────────────────────────────────────

@router.post("/tokenize")
async def tgi_tokenize(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    text   = body.get("inputs", "")
    tokens = text.split()
    return JSONResponse(content=[
        {"id": 1000 + i, "text": t, "special": False, "start": i * 6, "stop": i * 6 + len(t)}
        for i, t in enumerate(tokens)
    ])


# ── POST /decode ──────────────────────────────────────────────────────────────

@router.post("/decode")
async def tgi_decode(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    ids = body.get("ids", [])
    return JSONResponse(content={"text": f"decoded text from {len(ids)} token ids"})
