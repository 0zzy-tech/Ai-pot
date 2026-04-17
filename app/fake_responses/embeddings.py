"""
Deterministic fake embedding vectors.
Same input text always returns the same vector (consistency),
normalized to unit sphere to match real embedding behaviour.
"""

import hashlib
import math
import random
import time


def fake_embedding(text: str, dims: int = 768) -> list[float]:
    """Return a deterministic unit-normalized embedding vector."""
    seed = int(hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest(), 16)
    rng = random.Random(seed % (2**32))
    vec = [rng.gauss(0.0, 1.0) for _ in range(dims)]
    magnitude = math.sqrt(sum(x * x for x in vec))
    if magnitude == 0:
        magnitude = 1.0
    return [round(x / magnitude, 8) for x in vec]


def make_ollama_embeddings_response(model: str, prompt: str) -> dict:
    return {"embedding": fake_embedding(prompt)}


def make_openai_embeddings_response(model: str, inputs: list[str]) -> dict:
    return {
        "object": "list",
        "data": [
            {
                "object":    "embedding",
                "index":     i,
                "embedding": fake_embedding(text),
            }
            for i, text in enumerate(inputs)
        ],
        "model": model,
        "usage": {
            "prompt_tokens": sum(len(t.split()) for t in inputs),
            "total_tokens":  sum(len(t.split()) for t in inputs),
        },
    }
