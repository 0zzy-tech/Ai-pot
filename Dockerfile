# ─────────────────────────────────────────────────────────────────────────────
# AI Honeypot — multi-stage Dockerfile
# Supports: linux/amd64  linux/arm64  linux/arm/v7 (Raspberry Pi 32-bit)
#
# Build locally:
#   docker build -t ai-honeypot .
#
# Multi-arch with buildx:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64,linux/arm/v7 \
#     -t ghcr.io/0zzy-tech/ai-pot:latest --push .
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools (needed for some C-extension wheels on arm/v7)
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install into an isolated prefix so we can COPY only wheels into runtime
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="AI Honeypot"
LABEL org.opencontainers.image.description="Multi-platform AI API honeypot with live dashboard"
LABEL org.opencontainers.image.source="https://github.com/0zzy-tech/Ai-pot"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/        ./app/
COPY static/     ./static/
COPY templates/  ./templates/
COPY config.py   main.py ./

# Create a non-root user and the data directory for the SQLite database
RUN useradd -r -u 1000 -s /bin/false honeypot && \
    mkdir -p /data && \
    chown honeypot:honeypot /data /app

USER honeypot

# ── Runtime configuration (all overridable via -e / docker-compose env:) ──────
ENV HOST=0.0.0.0 \
    PORT=11434 \
    DB_PATH=/data/honeypot.db \
    ADMIN_USERNAME=admin \
    ADMIN_PASSWORD=changeme \
    ADMIN_PREFIX=/__admin \
    STREAM_WORD_DELAY_SECS=0.04 \
    MAX_REQUESTS_STORED=100000

# SQLite database lives on a named volume for persistence across container restarts
VOLUME ["/data"]

EXPOSE 11434

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/')" \
  || exit 1

CMD ["python", "main.py"]
