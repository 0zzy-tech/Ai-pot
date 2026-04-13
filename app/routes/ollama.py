"""
Fake Ollama API endpoints — port 11434.
All responses are realistic enough to pass as a real Ollama installation.
"""

import json
from typing import Optional

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.fake_responses.embeddings import make_ollama_embeddings_response
from app.fake_responses.generate import (
    stream_chat,
    stream_generate,
    stream_pull,
    stream_push,
)
from app.fake_responses.models_catalog import (
    get_ps_response,
    get_show_response,
    get_tags_response,
)
from app.models import (
    ChatRequest,
    CopyRequest,
    DeleteRequest,
    EmbeddingsRequest,
    GenerateRequest,
    PullRequest,
    PushRequest,
    ShowRequest,
)

router = APIRouter()


# ── Root ──────────────────────────────────────────────────────────────────────

@router.get("/")
async def root():
    return Response(content="Ollama is running", media_type="text/plain")


# ── Model listing ─────────────────────────────────────────────────────────────

@router.get("/api/tags")
async def api_tags():
    return JSONResponse(content=get_tags_response())


@router.get("/api/ps")
async def api_ps():
    return JSONResponse(content=get_ps_response())


# ── Model info ────────────────────────────────────────────────────────────────

@router.post("/api/show")
async def api_show(req: ShowRequest):
    return JSONResponse(content=get_show_response(req.name))


# ── Text generation ───────────────────────────────────────────────────────────

@router.post("/api/generate")
async def api_generate(req: GenerateRequest):
    if req.stream is False:
        # Non-streaming: collect all chunks and return as one JSON
        chunks = []
        async for chunk in stream_generate(req.model, req.prompt):
            chunks.append(chunk)
        # Last chunk contains the done=True response
        last = json.loads(chunks[-1].decode())
        last["response"] = "".join(
            json.loads(c.decode()).get("response", "") for c in chunks
        )
        return JSONResponse(content=last)

    return StreamingResponse(
        stream_generate(req.model, req.prompt),
        media_type="application/x-ndjson",
    )


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.post("/api/chat")
async def api_chat(req: ChatRequest):
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]

    if req.stream is False:
        chunks = []
        async for chunk in stream_chat(req.model, msgs):
            chunks.append(chunk)
        last = json.loads(chunks[-1].decode())
        full_content = "".join(
            json.loads(c.decode()).get("message", {}).get("content", "")
            for c in chunks
        )
        last["message"] = {"role": "assistant", "content": full_content}
        return JSONResponse(content=last)

    return StreamingResponse(
        stream_chat(req.model, msgs),
        media_type="application/x-ndjson",
    )


# ── Model management ──────────────────────────────────────────────────────────

@router.post("/api/pull")
async def api_pull(req: PullRequest):
    if req.stream is False:
        return JSONResponse(content={"status": "success"})
    return StreamingResponse(
        stream_pull(req.name),
        media_type="application/x-ndjson",
    )


@router.post("/api/push")
async def api_push(req: PushRequest):
    if req.stream is False:
        return JSONResponse(content={"status": "success"})
    return StreamingResponse(
        stream_push(req.name),
        media_type="application/x-ndjson",
    )


@router.delete("/api/delete")
async def api_delete(req: DeleteRequest):
    return Response(status_code=200)


@router.post("/api/copy")
async def api_copy(req: CopyRequest):
    return Response(status_code=200)


# ── Embeddings ────────────────────────────────────────────────────────────────

@router.post("/api/embeddings")
async def api_embeddings(req: EmbeddingsRequest):
    return JSONResponse(
        content=make_ollama_embeddings_response(req.model, req.prompt)
    )


# ── Blob operations (stubs) ───────────────────────────────────────────────────

@router.head("/api/blobs/{digest}")
async def api_blobs_head(digest: str):
    return Response(status_code=200)


@router.post("/api/blobs/{digest}")
async def api_blobs_post(digest: str, request: Request):
    return Response(status_code=200)
