"""
Fake Mistral AI API endpoints.
Mistral's API is OpenAI-compatible for chat/completions/embeddings,
but adds FIM (fill-in-the-middle) for code completion and
agent-specific endpoints.

Real additional endpoints (beyond OpenAI-compat covered by openai_compat.py):
  GET  /v1/models           (also in openai_compat, but returns Mistral model list)
  POST /v1/fim/completions  (code fill-in-the-middle)
  GET  /v1/agents           (Mistral Agents)
  POST /v1/agents/completions
"""

import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.fake_responses.generate import _pick_response, Config
import asyncio
import json

router = APIRouter()

_MISTRAL_MODELS = [
    {"id": "mistral-large-latest",     "created": 1715097600, "object": "model", "owned_by": "mistralai"},
    {"id": "mistral-small-latest",     "created": 1715097600, "object": "model", "owned_by": "mistralai"},
    {"id": "mistral-tiny",             "created": 1708387200, "object": "model", "owned_by": "mistralai"},
    {"id": "codestral-latest",         "created": 1717372800, "object": "model", "owned_by": "mistralai"},
    {"id": "open-mistral-7b",          "created": 1704067200, "object": "model", "owned_by": "mistralai"},
    {"id": "open-mixtral-8x7b",        "created": 1705190400, "object": "model", "owned_by": "mistralai"},
    {"id": "open-mixtral-8x22b",       "created": 1713398400, "object": "model", "owned_by": "mistralai"},
    {"id": "mistral-embed",            "created": 1706745600, "object": "model", "owned_by": "mistralai"},
]


# ── POST /v1/fim/completions (code fill-in-the-middle) ───────────────────────

@router.post("/v1/fim/completions")
async def mistral_fim(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt  = body.get("prompt", "")
    suffix  = body.get("suffix", "")
    model   = body.get("model", "codestral-latest")
    stream  = body.get("stream", False)

    # Generate a plausible code-fill response
    fill_text = "    result = process(data)\n    return result\n"

    if stream:
        return StreamingResponse(
            _fim_stream(model, fill_text),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    tok_in  = len(str(prompt).split()) + len(str(suffix).split())
    tok_out = len(fill_text.split())

    return JSONResponse(content={
        "id":      f"cmpl-{uuid.uuid4().hex[:24]}",
        "object":  "chat.completion",
        "created": int(time.time()),
        "model":   model,
        "choices": [
            {
                "index":         0,
                "message":       {"role": "assistant", "content": fill_text},
                "finish_reason": "stop",
                "delta":         {"content": ""},
            }
        ],
        "usage": {
            "prompt_tokens":     tok_in,
            "completion_tokens": tok_out,
            "total_tokens":      tok_in + tok_out,
        },
    })


async def _fim_stream(model: str, fill_text: str):
    lines = fill_text.split("\n")
    chunk_id = f"cmpl-{uuid.uuid4().hex[:24]}"

    for line in lines:
        if not line and line != lines[-1]:
            continue
        chunk = {
            "id":      chunk_id,
            "object":  "chat.completion.chunk",
            "created": int(time.time()),
            "model":   model,
            "choices": [{"index": 0, "delta": {"content": line + "\n"}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n".encode()
        await asyncio.sleep(0.05)

    final = {
        "id":      chunk_id,
        "object":  "chat.completion.chunk",
        "created": int(time.time()),
        "model":   model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final)}\n\n".encode()
    yield b"data: [DONE]\n\n"


# ── GET /v1/agents ────────────────────────────────────────────────────────────

@router.get("/v1/agents")
async def mistral_agents():
    return JSONResponse(content={
        "data": [
            {
                "id":          "ag:48e2b83f:20240523:code-assistant:6e0c2430",
                "object":      "agent",
                "name":        "Code Assistant",
                "description": "Helps with coding tasks",
                "model":       "codestral-latest",
                "instructions": "You are a helpful coding assistant.",
                "created_at":  1716422400,
            }
        ],
        "object": "list",
        "total":  1,
    })


# ── POST /v1/agents/completions ───────────────────────────────────────────────

@router.post("/v1/agents/completions")
async def mistral_agent_completion(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    messages = body.get("messages", [])
    agent_id = body.get("agent_id", "ag:default")
    stream   = body.get("stream", False)

    last_user = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    response_text = _pick_response(str(last_user))

    return JSONResponse(content={
        "id":      f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object":  "chat.completion",
        "created": int(time.time()),
        "model":   "codestral-latest",
        "choices": [
            {
                "index":         0,
                "message":       {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens":     sum(len(str(m.get("content", "")).split()) for m in messages),
            "completion_tokens": len(response_text.split()),
            "total_tokens":      sum(len(str(m.get("content", "")).split()) for m in messages) + len(response_text.split()),
        },
    })
