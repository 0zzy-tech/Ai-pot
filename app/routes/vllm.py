"""
vLLM-specific endpoints.

vLLM is largely OpenAI-compatible (handled by openai_compat.py) but exposes
a few unique endpoints for tokenisation and health checking that differ from
other platforms.

Port: 8000 (default vLLM)
"""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/ping")
async def ping():
    return JSONResponse({"message": "PONG"})


@router.get("/version")
async def version():
    return JSONResponse({"version": "0.6.3"})


@router.post("/v1/tokenize")
async def tokenize(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    prompt = body.get("prompt", body.get("text", ""))
    # Fake token IDs — roughly 1 token per 4 chars
    fake_tokens = list(range(1000, 1000 + max(1, len(str(prompt)) // 4)))
    return JSONResponse({
        "tokens":      fake_tokens,
        "count":       len(fake_tokens),
        "max_model_len": 131072,
    })


@router.post("/v1/detokenize")
async def detokenize(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    tokens = body.get("tokens", [])
    # Fake detokenisation — return placeholder text
    prompt = " ".join(["token"] * len(tokens)) if tokens else ""
    return JSONResponse({"prompt": prompt})
