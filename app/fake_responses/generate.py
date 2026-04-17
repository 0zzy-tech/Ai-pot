"""
Fake streaming text generation for Ollama and OpenAI-compatible APIs.
Responses are canned but convincing — word-by-word NDJSON streaming
at ~25 tokens/sec to mimic a real GPU-backed model.
"""

import asyncio
import json
import random
import time
from datetime import datetime, timezone
from typing import AsyncIterator

from config import Config

# Canned responses keyed by simple keyword detection
_CANNED_RESPONSES = [
    (
        ["hello", "hi", "hey", "greet"],
        "Hello! How can I assist you today? I'm ready to help with questions, "
        "analysis, coding, writing, or any other task you have in mind.",
    ),
    (
        ["code", "python", "javascript", "function", "script", "program"],
        "Sure! Here's a simple example:\n\n```python\ndef greet(name: str) -> str:\n"
        "    return f'Hello, {name}!'\n\nif __name__ == '__main__':\n"
        "    print(greet('World'))\n```\n\nLet me know if you'd like me to "
        "adjust the logic or add more functionality.",
    ),
    (
        ["explain", "what is", "describe", "tell me about", "how does"],
        "That's a great question. The concept you're asking about involves several "
        "interconnected ideas. At its core, the fundamental principle relates to how "
        "systems interact with their environment. To understand it fully, we need to "
        "consider both the theoretical foundations and practical applications. "
        "I'd be happy to go deeper into any specific aspect.",
    ),
    (
        ["summarize", "summary", "brief", "tldr"],
        "Here's a concise summary of the key points: The main topic covers several "
        "important aspects that can be broken down into core components. "
        "The primary takeaway is that understanding the fundamentals enables better "
        "decision-making in practice. Would you like me to expand on any area?",
    ),
    (
        ["translate", "french", "spanish", "german", "chinese", "japanese"],
        "Translation complete. The text has been rendered in the target language "
        "while preserving the original meaning and tone. "
        "Note that idiomatic expressions may vary by regional dialect.",
    ),
    (
        ["help", "assist", "support", "can you"],
        "Of course! I'm here to help. Please share more details about what you "
        "need, and I'll do my best to provide accurate and useful information. "
        "Whether it's a technical problem, creative task, or general question, "
        "I'm ready to assist.",
    ),
]

_DEFAULT_RESPONSE = (
    "I understand your request. Let me think through this carefully. "
    "Based on the information provided, there are several important considerations "
    "to keep in mind. First, we should establish the context clearly. "
    "Then we can work through the specifics systematically. "
    "Please let me know if you'd like me to elaborate on any particular aspect."
)


def _pick_response(prompt: str) -> str:
    prompt_lower = prompt.lower()
    for keywords, response in _CANNED_RESPONSES:
        if any(kw in prompt_lower for kw in keywords):
            return response
    return _DEFAULT_RESPONSE


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


async def stream_generate(model: str, prompt: str) -> AsyncIterator[bytes]:
    """Yields NDJSON bytes for Ollama /api/generate streaming."""
    response_text = _pick_response(prompt)
    words = response_text.split()
    start_ns = time.time_ns()

    for word in words:
        chunk = {
            "model":      model,
            "created_at": _now_iso(),
            "response":   word + " ",
            "done":       False,
        }
        yield (json.dumps(chunk) + "\n").encode()
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)

    eval_count = len(words)
    elapsed_ns = time.time_ns() - start_ns

    final = {
        "model":              model,
        "created_at":         _now_iso(),
        "response":           "",
        "done":               True,
        "context":            list(range(1, min(len(prompt.split()) + 1, 33))),
        "total_duration":     elapsed_ns,
        "load_duration":      12345678,
        "prompt_eval_count":  len(prompt.split()),
        "prompt_eval_duration": 234567890,
        "eval_count":         eval_count,
        "eval_duration":      elapsed_ns,
    }
    yield (json.dumps(final) + "\n").encode()


async def stream_chat(model: str, messages: list[dict]) -> AsyncIterator[bytes]:
    """Yields NDJSON bytes for Ollama /api/chat streaming."""
    last_user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    response_text = _pick_response(last_user)
    words = response_text.split()
    start_ns = time.time_ns()

    for word in words:
        chunk = {
            "model":      model,
            "created_at": _now_iso(),
            "message": {
                "role":    "assistant",
                "content": word + " ",
            },
            "done": False,
        }
        yield (json.dumps(chunk) + "\n").encode()
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)

    elapsed_ns = time.time_ns() - start_ns
    final = {
        "model":              model,
        "created_at":         _now_iso(),
        "message":            {"role": "assistant", "content": ""},
        "done":               True,
        "total_duration":     elapsed_ns,
        "load_duration":      12345678,
        "prompt_eval_count":  sum(len(m.get("content", "").split()) for m in messages),
        "eval_count":         len(words),
        "eval_duration":      elapsed_ns,
    }
    yield (json.dumps(final) + "\n").encode()


async def stream_pull(name: str) -> AsyncIterator[bytes]:
    """Fake model pull with progress events."""
    stages = [
        ("pulling manifest",        None,      None),
        ("pulling",                 "sha256:a80c4f17acd5", 0),
        ("pulling",                 "sha256:a80c4f17acd5", 25),
        ("pulling",                 "sha256:a80c4f17acd5", 50),
        ("pulling",                 "sha256:a80c4f17acd5", 75),
        ("pulling",                 "sha256:a80c4f17acd5", 100),
        ("verifying sha256 digest", None,      None),
        ("writing manifest",        None,      None),
        ("removing any unused layers", None,   None),
        ("success",                 None,      None),
    ]
    total = 2019393189
    for status, digest, pct in stages:
        chunk: dict = {"status": status}
        if digest:
            chunk["digest"] = digest
            chunk["total"] = total
            chunk["completed"] = int(total * pct / 100)
        yield (json.dumps(chunk) + "\n").encode()
        await asyncio.sleep(0.3)


async def stream_push(name: str) -> AsyncIterator[bytes]:
    """Fake model push with progress events."""
    stages = [
        "retrieving manifest",
        "starting upload",
        "pushing layer 1/2",
        "pushing layer 2/2",
        "pushing manifest",
        "success",
    ]
    for status in stages:
        yield (json.dumps({"status": status}) + "\n").encode()
        await asyncio.sleep(0.3)


# ── OpenAI-compatible helpers ─────────────────────────────────────────────────

def make_openai_chat_chunk(model: str, content: str, finish_reason=None) -> bytes:
    import uuid
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    data = {
        "id":      chunk_id,
        "object":  "chat.completion.chunk",
        "created": int(time.time()),
        "model":   model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(data)}\n\n".encode()


async def stream_openai_chat(model: str, messages: list[dict]) -> AsyncIterator[bytes]:
    """Server-sent events stream for OpenAI /v1/chat/completions."""
    last_user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    response_text = _pick_response(last_user)
    words = response_text.split()

    # Opening role chunk
    import uuid, time as _time
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': int(_time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n".encode()

    for word in words:
        yield make_openai_chat_chunk(model, word + " ")
        await asyncio.sleep(Config.STREAM_WORD_DELAY_SECS)

    yield make_openai_chat_chunk(model, "", finish_reason="stop")
    yield b"data: [DONE]\n\n"


def make_openai_chat_response(model: str, messages: list[dict]) -> dict:
    """Non-streaming OpenAI chat response."""
    import uuid, time as _time
    last_user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    content = _pick_response(last_user)
    return {
        "id":      f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object":  "chat.completion",
        "created": int(_time.time()),
        "model":   model,
        "choices": [
            {
                "index":         0,
                "message":       {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens":     len(last_user.split()),
            "completion_tokens": len(content.split()),
            "total_tokens":      len(last_user.split()) + len(content.split()),
        },
    }


def make_openai_completion_response(model: str, prompt: str) -> dict:
    import uuid, time as _time
    content = _pick_response(prompt)
    return {
        "id":      f"cmpl-{uuid.uuid4().hex[:24]}",
        "object":  "text_completion",
        "created": int(_time.time()),
        "model":   model,
        "choices": [
            {
                "text":          content,
                "index":         0,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens":     len(prompt.split()),
            "completion_tokens": len(content.split()),
            "total_tokens":      len(prompt.split()) + len(content.split()),
        },
    }
