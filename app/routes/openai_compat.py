"""
OpenAI-compatible API endpoints.
Many tools (LangChain, LlamaIndex, Open WebUI, etc.) point at Ollama's
OpenAI-compat layer — this captures all of them.
"""

import time
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.canary import get_canary_token
from app.fake_responses.embeddings import make_openai_embeddings_response
from app.fake_responses.generate import (
    make_openai_chat_response,
    make_openai_completion_response,
    stream_openai_chat,
)
from app.fake_responses.models_catalog import FAKE_MODELS
from app.models import (
    OpenAIChatRequest,
    OpenAICompletionRequest,
    OpenAIEmbeddingsRequest,
)

router = APIRouter(prefix="/v1")


# ── Model listing ─────────────────────────────────────────────────────────────

@router.get("/models")
async def list_models():
    models = []
    for i, m in enumerate(FAKE_MODELS):
        entry = {
            "id":       m["name"],
            "object":   "model",
            "created":  int(time.time()) - 86400,
            "owned_by": "library",
        }
        # Embed the canary token in the first model entry as a realistic-looking API key field.
        # If an attacker copies this key and reuses it, the classifier flags it CRITICAL.
        if i == 0:
            entry["permission"] = [{"api_key": get_canary_token()}]
        models.append(entry)
    return JSONResponse(content={"object": "list", "data": models})


@router.get("/models/{model_id:path}")
async def get_model(model_id: str):
    return JSONResponse(
        content={
            "id":       model_id,
            "object":   "model",
            "created":  int(time.time()) - 86400,
            "owned_by": "library",
        }
    )


# ── Chat completions ──────────────────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(req: OpenAIChatRequest):
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]

    if req.stream:
        return StreamingResponse(
            stream_openai_chat(req.model, msgs),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return JSONResponse(content=make_openai_chat_response(req.model, msgs))


# ── Text completions ──────────────────────────────────────────────────────────

@router.post("/completions")
async def completions(req: OpenAICompletionRequest):
    return JSONResponse(
        content=make_openai_completion_response(req.model, req.prompt)
    )


# ── Embeddings ────────────────────────────────────────────────────────────────

@router.post("/embeddings")
async def embeddings(req: OpenAIEmbeddingsRequest):
    if isinstance(req.input, list):
        inputs = [str(i) for i in req.input]
    else:
        inputs = [str(req.input)]
    return JSONResponse(
        content=make_openai_embeddings_response(req.model, inputs)
    )
