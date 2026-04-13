"""
Fake Anthropic Claude API endpoints.
Captures tools using the Anthropic SDK or direct API calls.

Real endpoints:
  POST /v1/messages           (current Messages API)
  POST /v1/complete           (legacy Text Completions API)
  GET  /v1/models
"""

import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.fake_responses.generate import _pick_response, _now_iso, Config
import asyncio
import json

router = APIRouter()

_CLAUDE_MODELS = [
    {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"},
    {"id": "claude-3-5-haiku-20241022",  "display_name": "Claude 3.5 Haiku"},
    {"id": "claude-3-opus-20240229",     "display_name": "Claude 3 Opus"},
    {"id": "claude-3-sonnet-20240229",   "display_name": "Claude 3 Sonnet"},
    {"id": "claude-3-haiku-20240307",    "display_name": "Claude 3 Haiku"},
    {"id": "claude-2.1",                 "display_name": "Claude 2.1"},
    {"id": "claude-instant-1.2",         "display_name": "Claude Instant 1.2"},
]


# ── GET /v1/models ─────────────────────────────────────────────────────────────

@router.get("/v1/models")
async def anthropic_list_models():
    return JSONResponse(content={
        "data": [
            {
                "id":           m["id"],
                "display_name": m["display_name"],
                "created_at":   "2024-01-01T00:00:00Z",
                "type":         "model",
            }
            for m in _CLAUDE_MODELS
        ]
    })


# ── POST /v1/messages ─────────────────────────────────────────────────────────

@router.post("/v1/messages")
async def anthropic_messages(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    model    = body.get("model", "claude-3-5-sonnet-20241022")
    messages = body.get("messages", [])
    stream   = body.get("stream", False)
    max_tok  = body.get("max_tokens", 1024)

    # Extract last user message for response selection
    last_user = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    if isinstance(last_user, list):
        # Content blocks format
        last_user = " ".join(
            block.get("text", "") for block in last_user if isinstance(block, dict)
        )

    response_text = _pick_response(str(last_user))
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    if stream:
        return StreamingResponse(
            _stream_messages(msg_id, model, response_text),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    input_tokens  = sum(
        len(str(m.get("content", "")).split()) for m in messages
    )
    output_tokens = len(response_text.split())

    return JSONResponse(content={
        "id":   msg_id,
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": response_text}],
        "model": model,
        "stop_reason":    "end_turn",
        "stop_sequence":  None,
        "usage": {
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
        },
    })


async def _stream_messages(msg_id: str, model: str, response_text: str):
    words = response_text.split()

    def _sse(event: str, data: dict) -> bytes:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()

    yield _sse("message_start", {
        "type":    "message_start",
        "message": {
            "id":      msg_id,
            "type":    "message",
            "role":    "assistant",
            "content": [],
            "model":   model,
            "stop_reason":   None,
            "stop_sequence": None,
            "usage":   {"input_tokens": 10, "output_tokens": 0},
        },
    })
    yield _sse("content_block_start", {
        "type":          "content_block_start",
        "index":         0,
        "content_block": {"type": "text", "text": ""},
    })
    yield _sse("ping", {"type": "ping"})

    for word in words:
        yield _sse("content_block_delta", {
            "type":  "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": word + " "},
        })
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)

    yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield _sse("message_delta", {
        "type":  "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": len(words)},
    })
    yield _sse("message_stop", {"type": "message_stop"})


# ── POST /v1/complete  (legacy API) ──────────────────────────────────────────

@router.post("/v1/complete")
async def anthropic_complete(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    model  = body.get("model", "claude-2.1")
    prompt = body.get("prompt", "")
    stream = body.get("stream", False)

    # Legacy format: "\n\nHuman: ...\n\nAssistant:"
    human_text = prompt.split("\n\nHuman:")[-1].split("\n\nAssistant:")[0].strip()
    response_text = _pick_response(human_text)

    if stream:
        return StreamingResponse(
            _stream_complete(model, response_text),
            media_type="text/event-stream",
        )

    return JSONResponse(content={
        "completion": " " + response_text,
        "stop_reason": "stop_sequence",
        "model":       model,
        "stop":        "\n\nHuman:",
        "log_id":      uuid.uuid4().hex,
    })


async def _stream_complete(model: str, response_text: str):
    for word in response_text.split():
        data = json.dumps({
            "completion":  " " + word,
            "stop_reason": None,
            "model":       model,
        })
        yield f"data: {data}\n\n".encode()
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)

    yield f"data: {json.dumps({'completion': '', 'stop_reason': 'stop_sequence', 'model': model})}\n\n".encode()
    yield b"data: [DONE]\n\n"
