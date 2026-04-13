"""
Pydantic models for Ollama and OpenAI-compatible request/response bodies.
"""

from typing import Any, Optional
from pydantic import BaseModel


# ── Ollama request models ──────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    model: str
    prompt: str = ""
    system: Optional[str] = None
    template: Optional[str] = None
    context: Optional[list[int]] = None
    stream: Optional[bool] = True
    raw: Optional[bool] = False
    options: Optional[dict[str, Any]] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = []
    stream: Optional[bool] = True
    options: Optional[dict[str, Any]] = None


class PullRequest(BaseModel):
    name: str
    insecure: Optional[bool] = False
    stream: Optional[bool] = True


class PushRequest(BaseModel):
    name: str
    insecure: Optional[bool] = False
    stream: Optional[bool] = True


class DeleteRequest(BaseModel):
    name: str


class ShowRequest(BaseModel):
    name: str


class CopyRequest(BaseModel):
    source: str
    destination: str


class EmbeddingsRequest(BaseModel):
    model: str
    prompt: str = ""


# ── OpenAI-compatible request models ──────────────────────────────────────────

class OpenAIMessage(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: str
    messages: list[OpenAIMessage] = []
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None


class OpenAICompletionRequest(BaseModel):
    model: str
    prompt: str = ""
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None


class OpenAIEmbeddingsRequest(BaseModel):
    model: str
    input: Any = ""
