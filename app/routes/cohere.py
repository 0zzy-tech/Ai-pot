"""
Fake Cohere API endpoints.
Cohere is widely used for embeddings, RAG, and reranking pipelines.

Real endpoints:
  POST /v1/chat
  POST /v1/generate        (legacy)
  POST /v1/embed
  POST /v1/rerank
  POST /v1/classify
  POST /v1/tokenize
  POST /v1/detokenize
  GET  /v1/models
"""

import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.fake_responses.generate import _pick_response, Config
from app.fake_responses.embeddings import fake_embedding
import asyncio
import json

router = APIRouter()

_COHERE_MODELS = [
    {"name": "command-r-plus-08-2024",  "endpoints": ["generate", "chat", "summarize"]},
    {"name": "command-r-08-2024",       "endpoints": ["generate", "chat", "summarize"]},
    {"name": "command-r",               "endpoints": ["generate", "chat", "summarize"]},
    {"name": "command",                 "endpoints": ["generate", "chat", "summarize"]},
    {"name": "command-light",           "endpoints": ["generate", "chat", "summarize"]},
    {"name": "embed-english-v3.0",      "endpoints": ["embed"]},
    {"name": "embed-multilingual-v3.0", "endpoints": ["embed"]},
    {"name": "rerank-english-v3.0",     "endpoints": ["rerank"]},
    {"name": "rerank-multilingual-v3.0","endpoints": ["rerank"]},
]


# ── GET /v1/models ─────────────────────────────────────────────────────────────

@router.get("/v1/models")
async def cohere_models():
    return JSONResponse(content={
        "models": [
            {
                "name":      m["name"],
                "endpoints": m["endpoints"],
                "finetuned": False,
                "context_length": 128000,
                "tokenizer_url": f"https://storage.googleapis.com/cohere-public/tokenizers/{m['name']}.json",
            }
            for m in _COHERE_MODELS
        ]
    })


# ── POST /v1/chat ──────────────────────────────────────────────────────────────

@router.post("/v1/chat")
async def cohere_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    message   = body.get("message", "")
    model     = body.get("model", "command-r-plus-08-2024")
    stream    = body.get("stream", False)
    chat_hist = body.get("chat_history", [])

    response_text = _pick_response(str(message))

    if stream:
        return StreamingResponse(
            _cohere_chat_stream(response_text, model, chat_hist, message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return JSONResponse(content={
        "text":            response_text,
        "generation_id":   uuid.uuid4().hex,
        "finish_reason":   "COMPLETE",
        "chat_history": chat_hist + [
            {"role": "USER",      "message": message},
            {"role": "CHATBOT",   "message": response_text},
        ],
        "meta": {
            "api_version":    {"version": "1"},
            "billed_units":   {"input_tokens": len(message.split()), "output_tokens": len(response_text.split())},
            "tokens":         {"input_tokens": len(message.split()), "output_tokens": len(response_text.split())},
        },
    })


async def _cohere_chat_stream(response_text: str, model: str, history: list, message: str):
    words = response_text.split()

    yield json.dumps({
        "is_finished": False,
        "event_type":  "stream-start",
        "generation_id": uuid.uuid4().hex,
    }).encode() + b"\n"

    for word in words:
        yield json.dumps({
            "is_finished": False,
            "event_type":  "text-generation",
            "text":        word + " ",
        }).encode() + b"\n"
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)

    yield json.dumps({
        "is_finished":    True,
        "event_type":     "stream-end",
        "finish_reason":  "COMPLETE",
        "response": {
            "text":         response_text,
            "generation_id": uuid.uuid4().hex,
        },
    }).encode() + b"\n"


# ── POST /v1/generate (legacy) ────────────────────────────────────────────────

@router.post("/v1/generate")
async def cohere_generate(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt   = body.get("prompt", "")
    model    = body.get("model", "command")
    num_gens = body.get("num_generations", 1)

    response_text = _pick_response(str(prompt))

    return JSONResponse(content={
        "id":          uuid.uuid4().hex,
        "generations": [
            {
                "id":           uuid.uuid4().hex,
                "text":         response_text,
                "finish_reason": "COMPLETE",
                "likelihood":   None,
            }
            for _ in range(max(1, num_gens))
        ],
        "prompt": prompt[:200],
        "meta": {
            "api_version": {"version": "1"},
            "billed_units": {"input_tokens": len(str(prompt).split()), "output_tokens": len(response_text.split())},
        },
    })


# ── POST /v1/embed ─────────────────────────────────────────────────────────────

@router.post("/v1/embed")
async def cohere_embed(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    texts  = body.get("texts", [])
    model  = body.get("model", "embed-english-v3.0")
    input_type = body.get("input_type", "search_document")

    return JSONResponse(content={
        "id":         uuid.uuid4().hex,
        "embeddings": [fake_embedding(t, dims=1024) for t in texts],
        "texts":      texts,
        "model":      model,
        "usage": {
            "billed_units": {"input_tokens": sum(len(t.split()) for t in texts)},
            "tokens":       {"input_tokens": sum(len(t.split()) for t in texts)},
        },
    })


# ── POST /v1/rerank ────────────────────────────────────────────────────────────

@router.post("/v1/rerank")
async def cohere_rerank(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    query     = body.get("query", "")
    docs      = body.get("documents", [])
    model     = body.get("model", "rerank-english-v3.0")
    top_n     = body.get("top_n", len(docs))

    # Return docs in original order with fake relevance scores
    results = [
        {
            "index":            i,
            "relevance_score":  round(max(0.01, 0.95 - i * 0.15), 4),
            "document":         {"text": d} if isinstance(d, str) else d,
        }
        for i, d in enumerate(docs[:top_n])
    ]

    return JSONResponse(content={
        "id":      uuid.uuid4().hex,
        "results": results,
        "model":   model,
        "usage": {
            "billed_units": {"search_units": 1},
        },
    })


# ── POST /v1/classify ─────────────────────────────────────────────────────────

@router.post("/v1/classify")
async def cohere_classify(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    inputs  = body.get("inputs", [])
    model   = body.get("model", "embed-english-v3.0")

    return JSONResponse(content={
        "id":          uuid.uuid4().hex,
        "classifications": [
            {
                "id":          uuid.uuid4().hex,
                "input":       inp,
                "prediction":  "positive",
                "confidence":  0.87,
                "labels":      {"positive": {"confidence": 0.87}, "negative": {"confidence": 0.13}},
            }
            for inp in inputs
        ],
        "meta": {"api_version": {"version": "1"}},
    })


# ── POST /v1/tokenize ─────────────────────────────────────────────────────────

@router.post("/v1/tokenize")
async def cohere_tokenize(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    text  = body.get("text", "")
    words = str(text).split()
    return JSONResponse(content={
        "tokens":      list(range(10000, 10000 + len(words))),
        "token_strings": words,
        "meta":        {"api_version": {"version": "1"}},
    })


# ── POST /v1/detokenize ───────────────────────────────────────────────────────

@router.post("/v1/detokenize")
async def cohere_detokenize(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    tokens = body.get("tokens", [])
    return JSONResponse(content={
        "text": f"detokenized output from {len(tokens)} tokens",
        "meta": {"api_version": {"version": "1"}},
    })
