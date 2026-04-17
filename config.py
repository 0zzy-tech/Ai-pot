"""
Central configuration for the AI Honeypot.
All values can be overridden via environment variables — useful for Docker.
"""

import os


class Config:
    # ── Server ──────────────────────────────────────────────────────────────
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "11434"))   # Real Ollama port

    # ── Database ─────────────────────────────────────────────────────────────
    # Docker: mount a volume at /data and set DB_PATH=/data/honeypot.db
    DB_PATH = os.getenv("DB_PATH", "honeypot.db")

    # ── Geolocation ───────────────────────────────────────────────────────────
    GEO_API_URL = "http://ip-api.com/json/{ip}?fields=status,country,city,lat,lon,as"
    GEO_CACHE_TTL_HOURS    = int(os.getenv("GEO_CACHE_TTL_HOURS", "24"))
    GEO_MEMORY_CACHE_SIZE  = int(os.getenv("GEO_MEMORY_CACHE_SIZE", "1000"))

    # ── Risk thresholds ───────────────────────────────────────────────────────
    RAPID_REQUEST_THRESHOLD  = int(os.getenv("RAPID_REQUEST_THRESHOLD", "20"))
    RAPID_REQUEST_WINDOW_SECS = int(os.getenv("RAPID_REQUEST_WINDOW_SECS", "60"))
    REPEAT_IP_THRESHOLD      = int(os.getenv("REPEAT_IP_THRESHOLD", "5"))
    REPEAT_IP_WINDOW_SECS    = int(os.getenv("REPEAT_IP_WINDOW_SECS", "600"))
    LARGE_BODY_THRESHOLD     = int(os.getenv("LARGE_BODY_THRESHOLD", "5000"))

    # ── Body capture ──────────────────────────────────────────────────────────
    MAX_BODY_SIZE_BYTES = int(os.getenv("MAX_BODY_SIZE_BYTES", "10240"))  # 10 KB

    # ── Dashboard auth ────────────────────────────────────────────────────────
    # IMPORTANT: change ADMIN_PASSWORD before deploying (env var or edit here)
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
    ADMIN_PREFIX   = os.getenv("ADMIN_PREFIX", "/__admin")

    # ── Fake response behaviour ───────────────────────────────────────────────
    STREAM_WORD_DELAY_SECS = float(os.getenv("STREAM_WORD_DELAY_SECS", "0.04"))

    # ── Log retention ─────────────────────────────────────────────────────────
    MAX_REQUESTS_STORED = int(os.getenv("MAX_REQUESTS_STORED", "100000"))

    # ── Webhook alerting ──────────────────────────────────────────────────────
    # Comma-separated list of URLs to POST to on CRITICAL/HIGH events
    WEBHOOK_URLS        = [u.strip() for u in os.getenv("WEBHOOK_URLS", "").split(",") if u.strip()]
    WEBHOOK_RISK_LEVELS = set(os.getenv("WEBHOOK_RISK_LEVELS", "CRITICAL,HIGH").upper().split(","))
    WEBHOOK_FORMAT      = os.getenv("WEBHOOK_FORMAT", "json")  # slack | discord | json
    WEBHOOK_TIMEOUT_SECS = float(os.getenv("WEBHOOK_TIMEOUT_SECS", "5.0"))

    # ── Tarpit ────────────────────────────────────────────────────────────────
    # Per-service delay (seconds) before responding when tarpit is enabled
    TARPIT_DELAY_SECS = float(os.getenv("TARPIT_DELAY_SECS", "30.0"))

    # ── AbuseIPDB ─────────────────────────────────────────────────────────────
    # Get a free API key at https://www.abuseipdb.com/register
    ABUSEIPDB_API_KEY    = os.getenv("ABUSEIPDB_API_KEY", "")
    ABUSEIPDB_MAX_AGE_DAYS = int(os.getenv("ABUSEIPDB_MAX_AGE_DAYS", "90"))

    # ── Prometheus metrics ────────────────────────────────────────────────────
    METRICS_ENABLED = os.getenv("METRICS_ENABLED", "false").lower() == "true"
    METRICS_TOKEN   = os.getenv("METRICS_TOKEN", "")  # Optional Bearer auth

    # ── Auto-block ────────────────────────────────────────────────────────────
    # Automatically block IPs that trigger CRITICAL alerts repeatedly
    AUTO_BLOCK_ENABLED   = os.getenv("AUTO_BLOCK_ENABLED", "false").lower() == "true"
    AUTO_BLOCK_THRESHOLD = int(os.getenv("AUTO_BLOCK_THRESHOLD", "3"))   # CRITICAL hits
    AUTO_BLOCK_WINDOW    = int(os.getenv("AUTO_BLOCK_WINDOW", "300"))    # within seconds
