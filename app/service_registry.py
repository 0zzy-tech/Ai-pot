"""
Service registry — tracks which AI platform honeypots are enabled/disabled.

Design:
  - In-memory dict (_enabled_cache) is the fast path for every request
  - SQLite service_states table is the persistent store
  - Cache is loaded at startup (init_service_registry) and updated on toggle
  - get_service_for_path() is sync (called from middleware on every request)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Service definitions ────────────────────────────────────────────────────────
# Maps service_id → metadata + path ownership rules.
# A path belongs to the FIRST service whose rule matches it — mirrors FastAPI
# router registration order in main.py.

SERVICES: dict[str, dict] = {
    "ollama": {
        "label":       "Ollama",
        "description": "Native Ollama REST API — the most targeted AI endpoint",
        "icon":        "🦙",
        "port":        11434,
        "prefixes":    ["/api/"],
        "exact":       ["/"],
    },
    "openai_compat": {
        "label":       "OpenAI Compatible",
        "description": "OpenAI /v1/ layer (LangChain, LlamaIndex, Open WebUI…)",
        "icon":        "🤖",
        "port":        11434,
        "prefixes":    [],
        "exact":       [
            "/v1/models", "/v1/chat/completions",
            "/v1/completions", "/v1/embeddings",
        ],
    },
    "anthropic": {
        "label":       "Anthropic Claude",
        "description": "Claude Messages API — /v1/messages streaming",
        "icon":        "🧠",
        "port":        443,
        "prefixes":    [],
        "exact":       ["/v1/messages", "/v1/complete"],
    },
    "huggingface": {
        "label":       "HuggingFace TGI",
        "description": "Text Generation Inference server",
        "icon":        "🤗",
        "port":        8080,
        "prefixes":    [],
        "exact":       [
            "/generate", "/generate_stream", "/info",
            "/health", "/metrics", "/tokenize", "/decode",
        ],
    },
    "llamacpp": {
        "label":       "llama.cpp",
        "description": "llama.cpp HTTP server — native C++ backend",
        "icon":        "⚙️",
        "port":        8080,
        "prefixes":    [],
        "exact":       [
            "/completion", "/embedding", "/slots",
            "/props", "/infill", "/detokenize",
        ],
    },
    "textgenwebui": {
        "label":       "Text Gen WebUI",
        "description": "oobabooga text-generation-webui",
        "icon":        "💬",
        "port":        7860,
        "prefixes":    ["/api/v1/"],
        "exact":       [],
    },
    "cohere": {
        "label":       "Cohere",
        "description": "Cohere generate, embed, rerank & classify",
        "icon":        "🎯",
        "port":        443,
        "prefixes":    [],
        "exact":       [
            "/v1/chat", "/v1/generate", "/v1/embed",
            "/v1/rerank", "/v1/classify",
            "/v1/tokenize", "/v1/detokenize",
        ],
    },
    "mistral": {
        "label":       "Mistral AI",
        "description": "Mistral FIM code completion and Agents API",
        "icon":        "🌊",
        "port":        443,
        "prefixes":    [],
        "exact":       [
            "/v1/fim/completions",
            "/v1/agents", "/v1/agents/completions",
        ],
    },
    "gemini": {
        "label":       "Google Gemini",
        "description": "Google Generative AI / Vertex AI REST API",
        "icon":        "✨",
        "port":        443,
        "prefixes":    ["/v1beta/"],
        "exact":       [],
    },
    "stablediffusion": {
        "label":       "Stable Diffusion",
        "description": "Automatic1111 / FORGE WebUI image generation",
        "icon":        "🎨",
        "port":        7860,
        "prefixes":    ["/sdapi/"],
        "exact":       [],
    },
    "comfyui": {
        "label":       "ComfyUI",
        "description": "ComfyUI node-based image generation pipeline",
        "icon":        "🎭",
        "port":        8188,
        "prefixes":    ["/history/", "/object_info/"],
        "exact":       [
            "/system_stats", "/object_info", "/queue",
            "/prompt", "/interrupt", "/free", "/view", "/history",
        ],
    },
    "localai": {
        "label":       "LocalAI",
        "description": "LocalAI audio, TTS and image generation extensions",
        "icon":        "🏠",
        "port":        8080,
        "prefixes":    [],
        "exact":       [
            "/readyz", "/healthz", "/tts",
            "/v1/audio/transcriptions", "/v1/audio/translations", "/v1/audio/speech",
            "/v1/images/generations", "/v1/images/edits", "/v1/images/variations",
            "/v1/backends", "/v1/backend/monitor", "/v1/backend/shutdown",
        ],
    },
    "vllm": {
        "label":       "vLLM",
        "description": "vLLM high-throughput inference server (OpenAI-compatible)",
        "icon":        "⚡",
        "port":        8000,
        "prefixes":    [],
        "exact":       ["/ping", "/version", "/v1/tokenize", "/v1/detokenize"],
    },
    "lmstudio": {
        "label":       "LM Studio",
        "description": "LM Studio native API — popular local AI desktop app",
        "icon":        "🖥️",
        "port":        1234,
        "prefixes":    ["/api/v0/"],
        "exact":       [],
    },
}

# ── Paths that are NEVER blocked (internal / dashboard / WebSocket) ────────────
_INTERNAL_PREFIXES = ("/__admin", "/static", "/ws")

# ── In-memory enable/disable cache (True = enabled) ───────────────────────────
_enabled_cache: dict[str, bool] = {sid: True for sid in SERVICES}

# ── In-memory tarpit cache (True = tarpitted) ─────────────────────────────────
_tarpit_cache: dict[str, bool] = {sid: False for sid in SERVICES}

# ── In-memory blocked IP set ───────────────────────────────────────────────────
_blocked_ips: set[str] = set()

# ── In-memory allowed IP set (never logged / blocked) ─────────────────────────
_allowed_ips: set[str] = set()

# ── In-memory IP notes cache ───────────────────────────────────────────────────
_ip_notes: dict[str, str] = {}


# ── Path → service lookup (sync, fast) ────────────────────────────────────────

def get_service_for_path(path: str) -> Optional[str]:
    """Return the service_id that owns this path, or None for unknown/internal."""
    for sid, defn in SERVICES.items():
        if path in defn["exact"]:
            return sid
        for prefix in defn["prefixes"]:
            if path.startswith(prefix):
                return sid
    return None


def is_path_enabled(path: str) -> bool:
    """Sync check — safe to call from the ASGI middleware."""
    # Internal paths are always allowed
    if any(path.startswith(p) for p in _INTERNAL_PREFIXES):
        return True
    sid = get_service_for_path(path)
    if sid is None:
        return True   # Unknown paths pass through (logged as 'scanning')
    return _enabled_cache.get(sid, True)


def is_service_enabled(service_id: str) -> bool:
    return _enabled_cache.get(service_id, True)


def is_service_tarpitted(service_id: str) -> bool:
    return _tarpit_cache.get(service_id, False)


def is_path_tarpitted(path: str) -> bool:
    """Sync check — safe to call from the ASGI middleware."""
    sid = get_service_for_path(path)
    if sid is None:
        return False
    return _tarpit_cache.get(sid, False)


# ── DB-backed persistence ──────────────────────────────────────────────────────

def is_ip_blocked(ip: str) -> bool:
    """Sync check — safe to call from the ASGI middleware."""
    return ip in _blocked_ips


def is_ip_allowed(ip: str) -> bool:
    """Sync check — safe to call from the ASGI middleware."""
    return ip in _allowed_ips


def get_ip_note(ip: str) -> Optional[str]:
    """Sync — returns the operator note for this IP, or None."""
    return _ip_notes.get(ip)


async def init_ip_blocklist() -> None:
    """Load persisted blocked IPs from DB into in-memory set at startup."""
    from app.database import get_blocked_ips as db_get_blocked_ips
    rows = await db_get_blocked_ips()
    for row in rows:
        _blocked_ips.add(row["ip"])
    logger.info("IP blocklist loaded — %d blocked IPs", len(_blocked_ips))


async def block_ip(ip: str, reason: str) -> None:
    """Block an IP — updates in-memory set immediately, persists to DB."""
    from app.database import add_blocked_ip
    _blocked_ips.add(ip)
    await add_blocked_ip(ip, reason)
    logger.info("IP blocked: %s (%s)", ip, reason)


async def unblock_ip(ip: str) -> None:
    """Unblock an IP — updates in-memory set immediately, removes from DB."""
    from app.database import remove_blocked_ip
    _blocked_ips.discard(ip)
    await remove_blocked_ip(ip)
    logger.info("IP unblocked: %s", ip)


async def init_ip_allowlist() -> None:
    """Load persisted allowed IPs from DB into in-memory set at startup."""
    from app.database import get_allowed_ips as db_get_allowed_ips
    rows = await db_get_allowed_ips()
    for row in rows:
        _allowed_ips.add(row["ip"])
    logger.info("IP allowlist loaded — %d allowed IPs", len(_allowed_ips))


async def allow_ip(ip: str, label: str) -> None:
    """Allow an IP — updates in-memory set immediately, persists to DB."""
    from app.database import add_allowed_ip
    _allowed_ips.add(ip)
    await add_allowed_ip(ip, label)
    logger.info("IP allowed: %s (%s)", ip, label)


async def unallow_ip(ip: str) -> None:
    """Remove an IP from the allow-list."""
    from app.database import remove_allowed_ip
    _allowed_ips.discard(ip)
    await remove_allowed_ip(ip)
    logger.info("IP removed from allowlist: %s", ip)


async def init_ip_notes() -> None:
    """Load all operator IP notes from DB into in-memory dict at startup."""
    from app.database import get_all_ip_notes
    notes = await get_all_ip_notes()
    _ip_notes.update(notes)
    logger.info("IP notes loaded — %d notes", len(_ip_notes))


async def set_ip_note(ip: str, note: str) -> None:
    """Upsert an operator note for an IP — updates cache + DB."""
    from app.database import upsert_ip_note
    _ip_notes[ip] = note
    await upsert_ip_note(ip, note)


async def delete_ip_note(ip: str) -> None:
    """Delete the operator note for an IP."""
    from app.database import delete_ip_note
    _ip_notes.pop(ip, None)
    await delete_ip_note(ip)


async def init_service_registry() -> None:
    """Called once at startup — load persisted states from DB into cache."""
    from app.database import get_db

    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT name, enabled, tarpitted FROM service_states"
        )).fetchall()

    for row in rows:
        sid = row["name"]
        if sid in _enabled_cache:
            _enabled_cache[sid] = bool(row["enabled"])
        if sid in _tarpit_cache:
            _tarpit_cache[sid] = bool(row["tarpitted"])

    await init_ip_blocklist()
    await init_ip_allowlist()
    await init_ip_notes()

    logger.info(
        "Service registry loaded — %d enabled / %d disabled / %d tarpitted",
        sum(_enabled_cache.values()),
        sum(not v for v in _enabled_cache.values()),
        sum(_tarpit_cache.values()),
    )


async def reset_all_services() -> None:
    """Re-enable all services — updates cache immediately and clears persisted states."""
    for sid in SERVICES:
        _enabled_cache[sid] = True

    from app.database import get_db, _write_lock
    async with _write_lock:
        async with get_db() as db:
            await db.execute("DELETE FROM service_states")
            await db.commit()
    logger.info("All services reset to enabled")


async def set_service_enabled(service_id: str, enabled: bool) -> None:
    """Toggle a service on/off — updates cache immediately, persists to DB."""
    if service_id not in SERVICES:
        raise ValueError(f"Unknown service: {service_id!r}")

    from app.database import get_db, _write_lock

    # Update cache first (sync, immediate effect on all requests)
    _enabled_cache[service_id] = enabled

    # Persist — include tarpitted to avoid zeroing it on REPLACE
    tarpitted = _tarpit_cache.get(service_id, False)
    async with _write_lock:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO service_states (name, enabled, tarpitted) VALUES (?, ?, ?)",
                (service_id, 1 if enabled else 0, 1 if tarpitted else 0),
            )
            await db.commit()

    logger.info("Service %r %s", service_id, "enabled" if enabled else "disabled")


async def set_service_tarpitted(service_id: str, tarpitted: bool) -> None:
    """Toggle tarpit for a service — updates cache immediately, persists to DB."""
    if service_id not in SERVICES:
        raise ValueError(f"Unknown service: {service_id!r}")

    from app.database import get_db, _write_lock

    _tarpit_cache[service_id] = tarpitted

    enabled = _enabled_cache.get(service_id, True)
    async with _write_lock:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO service_states (name, enabled, tarpitted) VALUES (?, ?, ?)",
                (service_id, 1 if enabled else 0, 1 if tarpitted else 0),
            )
            await db.commit()

    logger.info("Service %r tarpit %s", service_id, "enabled" if tarpitted else "disabled")


def get_all_service_states() -> list[dict]:
    """Sync snapshot of all service states + metadata (no DB call needed)."""
    return [
        {
            "id":          sid,
            "label":       defn["label"],
            "description": defn["description"],
            "icon":        defn["icon"],
            "port":        defn["port"],
            "enabled":     _enabled_cache.get(sid, True),
            "tarpitted":   _tarpit_cache.get(sid, False),
        }
        for sid, defn in SERVICES.items()
    ]
