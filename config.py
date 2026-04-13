"""
Central configuration for the AI Honeypot.
All tuneable parameters live here — edit before deploying.
"""

class Config:
    # ── Server ─────────────────────────────────────────────────────────────
    HOST = "0.0.0.0"
    PORT = 11434          # Real Ollama port — critical for honeypot effectiveness

    # ── Database ───────────────────────────────────────────────────────────
    DB_PATH = "honeypot.db"

    # ── Geolocation ────────────────────────────────────────────────────────
    GEO_API_URL = "http://ip-api.com/json/{ip}?fields=status,country,city,lat,lon,as"
    GEO_CACHE_TTL_HOURS = 24
    GEO_MEMORY_CACHE_SIZE = 1000

    # ── Risk thresholds ────────────────────────────────────────────────────
    RAPID_REQUEST_THRESHOLD = 20   # requests from same IP within window → CRITICAL
    RAPID_REQUEST_WINDOW_SECS = 60
    REPEAT_IP_THRESHOLD = 5        # requests in short window → MEDIUM
    REPEAT_IP_WINDOW_SECS = 600
    LARGE_BODY_THRESHOLD = 5000    # bytes; above this → MEDIUM

    # ── Body capture ───────────────────────────────────────────────────────
    MAX_BODY_SIZE_BYTES = 10240    # 10 KB — prevent RAM exhaustion

    # ── Dashboard auth (change before deploying!) ──────────────────────────
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "changeme"
    ADMIN_PREFIX   = "/__admin"

    # ── Fake response behaviour ────────────────────────────────────────────
    STREAM_WORD_DELAY_SECS = 0.04  # Simulates ~25 tokens/sec (mid-tier GPU)

    # ── Log retention ──────────────────────────────────────────────────────
    MAX_REQUESTS_STORED = 100_000  # Oldest rows pruned after this
