# AI Honeypot

A lightweight honeypot that simultaneously masquerades as **11 different AI API servers**, capturing and classifying every request on a live dashboard with a global attack map.

Designed to run on a Raspberry Pi or any Ubuntu server. Ships as a multi-architecture Docker image (`amd64` · `arm64` · `arm/v7`).

---

## Dashboard Preview

```
┌─────────────────────────────────────────────────────────────────────┐
│  🛡 AI HONEYPOT MONITOR                               ● LIVE        │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────────┤
│ Total    │ Last 24h │ Critical │ High     │ Medium   │ Unique IPs  │
│ 14,832   │ 1,204    │ 87       │ 342      │ 891      │ 2,341       │
├──────────────────────────────┬──────────────────────────────────────┤
│                              │ Time     IP           Risk  Country  │
│   🌍 World Map               │ 14:32:01 185.220.x.x  CRIT  Russia  │
│   (risk-coloured pins)       │ 14:31:58 103.21.x.x   HIGH  China   │
│                              │ 14:31:55 45.33.x.x    MED   US      │
├──────────┬───────────────────┴──────────────────────────────────────┤
│ Risk Pie │ Category Bar         │ 24-Hour Timeline                  │
├──────────┴──────────────────────┴───────────────────────────────────┤
│  Simulated Platforms                                                 │
│  🦙 Ollama [ON] 🤖 OpenAI [ON] 🧠 Anthropic [OFF] 🤗 HF TGI [ON] │
│  ⚙️ llama.cpp [ON] 💬 TextGenUI [ON] 🎯 Cohere [ON] 🌊 Mistral [ON]│
│  ✨ Gemini [ON]  🎨 StableDiff [ON]  🎭 ComfyUI [ON]  🏠 LocalAI [ON]│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

- **11 fake AI platform APIs** — each responds convincingly on the same port
- **Streaming responses** — word-by-word token streaming at realistic GPU speed (~25 tok/s)
- **Risk classification** — CRITICAL / HIGH / MEDIUM / LOW with 30+ attack patterns
- **Per-service toggle** — enable or disable any platform from the dashboard; changes take effect instantly and persist across restarts
- **IP geolocation** — country, city and coordinates via ip-api.com (2-layer cache)
- **Live dashboard** — world map with risk-coloured pins, request feed, charts, timeline
- **Real-time WebSocket push** — dashboard updates on every request, no polling
- **Multi-arch Docker image** — `linux/amd64`, `linux/arm64`, `linux/arm/v7`
- **Lightweight** — single async worker, SQLite only, <384 MB RAM on Raspberry Pi 4

---

## Simulated Platforms

| # | Platform | Endpoints captured |
|---|---|---|
| 1 | **Ollama** | `/api/generate`, `/api/chat`, `/api/pull`, `/api/tags`, + 8 more |
| 2 | **OpenAI Compatible** | `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/models` |
| 3 | **Anthropic Claude** | `/v1/messages` (SSE streaming), `/v1/complete` (legacy) |
| 4 | **HuggingFace TGI** | `/generate`, `/generate_stream`, `/info`, `/metrics`, `/tokenize` |
| 5 | **llama.cpp** | `/completion`, `/embedding`, `/slots`, `/infill` (FIM), `/props` |
| 6 | **Text Gen WebUI** | `/api/v1/generate`, `/api/v1/chat`, `/api/v1/model`, `/api/v1/token-count` |
| 7 | **Cohere** | `/v1/chat`, `/v1/generate`, `/v1/embed`, `/v1/rerank`, `/v1/classify` |
| 8 | **Mistral AI** | `/v1/fim/completions`, `/v1/agents`, `/v1/agents/completions` |
| 9 | **Google Gemini** | `/v1beta/models/{model}:generateContent` + embed, stream, countTokens |
| 10 | **Stable Diffusion WebUI** | `/sdapi/v1/txt2img`, `/sdapi/v1/img2img`, full options/progress/models suite |
| 11 | **ComfyUI** | `/prompt`, `/system_stats`, `/queue`, `/history`, `/object_info` |
| +  | **LocalAI extensions** | `/v1/audio/transcriptions`, `/v1/images/generations`, `/tts`, `/v1/backends` |

---

## Quick Start

### Docker (recommended)

```bash
# Pull and run — change ADMIN_PASSWORD before exposing to the internet
docker run -d \
  --name ai-honeypot \
  -p 11434:11434 \
  -v honeypot-data:/data \
  -e ADMIN_PASSWORD=mysecretpassword \
  ghcr.io/0zzy-tech/ai-pot:latest
```

### Docker Compose

```bash
git clone https://github.com/0zzy-tech/Ai-pot
cd Ai-pot

# Set a strong password (required before exposing to internet)
ADMIN_PASSWORD=mysecretpassword docker compose up -d

# View logs
docker compose logs -f
```

Dashboard: `http://<host-ip>:11434/__admin`

### Bare Metal (Raspberry Pi / Ubuntu)

```bash
git clone https://github.com/0zzy-tech/Ai-pot
cd Ai-pot

sudo ./setup.sh          # installs venv, systemd service, opens UFW port
sudo systemctl start ai-honeypot
```

Dashboard: `http://<pi-ip>:11434/__admin`  
Default login: `admin` / `changeme`

### Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
# Dashboard: http://localhost:11434/__admin
```

---

## Configuration

All settings are configurable via environment variables (ideal for Docker) or by editing `config.py`.

| Variable | Default | Description |
|---|---|---|
| `PORT` | `11434` | Listen port — matches real Ollama for honeypot effect |
| `ADMIN_USERNAME` | `admin` | Dashboard login username |
| `ADMIN_PASSWORD` | `changeme` | **Change this before deploying** |
| `ADMIN_PREFIX` | `/__admin` | Dashboard URL prefix |
| `DB_PATH` | `honeypot.db` | SQLite path (`/data/honeypot.db` in Docker) |
| `RAPID_REQUEST_THRESHOLD` | `20` | Requests/60 s from one IP → CRITICAL |
| `REPEAT_IP_THRESHOLD` | `5` | Requests/10 min from one IP → MEDIUM |
| `LARGE_BODY_THRESHOLD` | `5000` | Body bytes above this → MEDIUM |
| `STREAM_WORD_DELAY_SECS` | `0.04` | Per-word delay in fake streaming (~25 tok/s) |
| `MAX_REQUESTS_STORED` | `100000` | SQLite row cap (oldest rows pruned) |
| `GEO_CACHE_TTL_HOURS` | `24` | IP geolocation cache lifetime |

---

## Risk Classification

| Level | Colour | Triggers |
|---|---|---|
| **CRITICAL** | 🔴 | Jailbreak / prompt injection, code execution (`exec`, `os.system`, `subprocess`), path traversal, SQL injection, mass scanning (>20 req/60 s) |
| **HIGH** | 🟠 | Model management (`/api/pull`, `/api/push`, `/api/delete`), scanner user-agents (nikto, sqlmap, nmap…), sensitive path segments (admin, secret, .env…) |
| **MEDIUM** | 🟡 | Embeddings & reranking, image generation, audio transcription, repeated IPs (>5/10 min), unknown model names, large bodies (>5 KB) |
| **LOW** | 🟢 | Normal inference, chat, model listing, enumeration |

---

## Request Categories

| Category | What it means |
|---|---|
| `inference` | Text generation / chat completions |
| `openai_compat` | OpenAI-compatible API calls |
| `anthropic` | Claude Messages API calls |
| `model_management` | Pull, push, delete, copy models |
| `embeddings` | Vector embedding requests |
| `rerank` | Cohere-style reranking (RAG pipelines) |
| `image_generation` | Stable Diffusion / ComfyUI / DALL-E |
| `audio_transcription` | Whisper / TTS requests |
| `code_completion` | FIM (fill-in-the-middle) requests |
| `model_info` | Model metadata / show / props |
| `enumeration` | Listing models, health checks |
| `scanning` | Unknown paths — active scanners |
| `attack` | CRITICAL pattern matched in body |

---

## Per-Service Toggle

Every simulated platform can be independently switched on or off from the **Simulated Platforms** panel at the bottom of the dashboard.

- **Disabled services return `404`** — the attacker sees nothing, as if the service doesn't exist
- **Requests to disabled services are still logged** — the honeypot intelligence is preserved
- **State persists** — toggle states survive container/service restarts (stored in SQLite)
- **Multi-tab sync** — toggling in one browser tab updates all other open tabs via WebSocket

---

## Docker Details

### Multi-Architecture Build

The GitHub Actions workflow (`.github/workflows/docker-build.yml`) automatically builds for all three architectures on every push to `main`:

| Architecture | Use case |
|---|---|
| `linux/amd64` | x86-64 servers, desktops, VMs |
| `linux/arm64` | Raspberry Pi 4/5 (64-bit OS), AWS Graviton, Apple Silicon |
| `linux/arm/v7` | Raspberry Pi 2/3 (32-bit Raspberry Pi OS) |

### Manual Multi-Arch Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  -t ghcr.io/0zzy-tech/ai-pot:latest \
  --push .
```

### Image Security

- Runs as non-root user `honeypot` (UID 1000)
- No secrets baked in — all credentials passed via environment variables
- Multi-stage build keeps the final image minimal (~200 MB)

---

## Architecture

```
Attacker
    │
    ▼ Port 11434
┌────────────────────────────────────────────────────────┐
│  FastAPI Middleware                                     │
│    1. Read body                                        │
│    2. Service gate — disabled service? → 404 (logged)  │
│    3. Route to matching fake handler                   │
│    4. asyncio.create_task(log_request) ← never blocks  │
└───────────┬────────────────────────────────────────────┘
            │
   ┌────────▼─────────┐
   │  Logger pipeline  │
   │  ├─ Classifier    │  sync regex → (category, risk, flags)
   │  ├─ Geolocator    │  async, 2-layer cache (memory + SQLite)
   │  ├─ SQLite write  │  aiosqlite, single write lock
   │  └─ WS broadcast  │  fan-out to all dashboard clients
   └────────┬──────────┘
            │ WebSocket
   ┌────────▼──────────┐
   │  Dashboard        │  /__admin  (HTTP Basic Auth)
   │  ├─ World map     │  Leaflet + CartoDB dark tiles
   │  ├─ Request feed  │  live scrolling table
   │  ├─ Charts        │  risk pie, category bar, 24h timeline
   │  └─ Service panel │  per-platform on/off toggles
   └───────────────────┘
```

---

## Service Management

### Docker
```bash
docker compose up -d          # start
docker compose down           # stop
docker compose restart        # restart
docker compose logs -f        # live logs
docker compose pull && docker compose up -d  # update to latest
```

### Systemd (bare metal)
```bash
sudo systemctl start   ai-honeypot
sudo systemctl stop    ai-honeypot
sudo systemctl restart ai-honeypot
sudo journalctl -u ai-honeypot -f
```
