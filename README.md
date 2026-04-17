# AI Honeypot

A lightweight honeypot that simultaneously masquerades as **13 different AI API servers**, capturing and classifying every request on a live dashboard with a global attack map.

Designed to run on a Raspberry Pi or any Ubuntu server. Ships as a multi-architecture Docker image (`amd64` · `arm64` · `arm/v7`).

---

## Dashboard Preview

```
┌─────────────────────────────────────────────────────────────────────┐
│  🛡 AI HONEYPOT MONITOR          ⬇ Threat Report      ● LIVE       │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────────┤
│ Total    │ Last 24h │ Critical │ High     │ Medium   │ Unique IPs  │
│ 14,832   │ 1,204    │ 87       │ 342      │ 891      │ 2,341       │
├──────────────────────────────┬──────────────────────────────────────┤
│                              │ 🔍 Search IP, path, body, country…  │
│   🌍 World Map               ├──────────────────────────────────────┤
│   (risk-coloured pins)       │ Time     IP*          Risk  Country  │
│                              │ 14:32:01 185.220.x.x● CRIT  Russia  │
│                              │ 14:31:58 103.21.x.x   HIGH  China   │
│                              │ 14:31:55 45.33.x.x    MED   US      │
│                              │  * click row → body/headers modal   │
├──────────┬───────────────────┴──────────────────────────────────────┤
│ Risk Pie │ Category Bar         │ 24-Hour Timeline                  │
├──────────┴──────────────────────┴───────────────────────────────────┤
│  📈 7-Day Trend (stacked CRIT/HIGH/MED/LOW per day)                 │
│  🕐 Hour-of-Day Heatmap (7×24 grid — when do attacks peak?)         │
├─────────────────────────────────────────────────────────────────────┤
│  Simulated Platforms  (toggle to enable/disable · TRAP to tarpit)   │
│  🦙 Ollama [ON][—] 🤖 OpenAI [ON][TRAP] 🧠 Anthropic [OFF][—]     │
│  ⚡ vLLM [ON][—] 🖥️ LM Studio [ON][—]  💬 TextGenUI [ON][—]        │
├─────────────────────────────────────────────────────────────────────┤
│  🔍 Intelligence                                                     │
│  Webhook Alerts: ✓ Active · 1 URL · Format: slack · CRITICAL,HIGH  │
│  Canary Token:   sk-pot-a1b2c3d4e5f6g7h8    [Copy]                 │
├─────────────────────────────────────────────────────────────────────┤
│  🚫 Blocked IPs  [3]  Auto-block: on                                │
│  185.220.x.x  auto: 3 criticals in 300s   2026-04-17  [Unblock]   │
└─────────────────────────────────────────────────────────────────────┘
* Click any IP to open per-IP session drawer · ● = high AbuseIPDB score
```

---

## Features

- **13 fake AI platform APIs** — each responds convincingly on the same port
- **Streaming responses** — word-by-word token streaming at realistic GPU speed (~25 tok/s)
- **Risk classification** — CRITICAL / HIGH / MEDIUM / LOW with 40+ attack patterns
- **Enhanced threat detection** — AWS/GCP/Azure credential exposure, SSRF, template injection, NoSQL injection, GraphQL introspection, base64-encoded payloads, credential stuffing
- **IP blocking** — manual block from dashboard/modal/drawer, or auto-block IPs that repeatedly trigger CRITICAL alerts
- **Per-service toggle** — enable or disable any platform from the dashboard; changes take effect instantly and persist across restarts
- **Tarpit mode** — per-service delay (default 30 s) that wastes attacker time before responding
- **Canary tokens** — fake API key embedded in `/v1/models`; any attacker who reuses it is instantly flagged CRITICAL
- **Webhook alerting** — HTTP POST to Slack, Discord, or generic JSON endpoints on CRITICAL/HIGH events
- **AbuseIPDB integration** — reputation score and Tor detection for every attacker IP (optional)
- **IP geolocation** — country, city and coordinates via ip-api.com (2-layer cache)
- **Live dashboard** — world map with risk-coloured pins, request feed, charts, timeline
- **Attack intelligence charts** — 7-day trend chart and hour-of-day heatmap showing when attacks peak
- **Real-time WebSocket push** — dashboard updates on every request, no polling
- **Request body viewer** — click any feed row to inspect headers, prettified JSON body, and flagged patterns; copy as cURL in one click
- **Request search** — full-text search across IP, path, body, and country in the feed
- **Per-IP session view** — click any IP to open a slide-out drawer with its complete request timeline
- **Threat report** — one-click self-contained HTML download with top IPs, paths, patterns, and geo breakdown
- **Prometheus metrics** — optional `/metrics` endpoint for Grafana / alertmanager integration
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
| 12 | **vLLM** | `/ping`, `/version`, `/v1/tokenize`, `/v1/detokenize` |
| 13 | **LM Studio** | `/api/v0/models`, `/api/v0/chat/completions`, `/api/v0/embeddings`, `/api/v0/system` |
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
| `TARPIT_DELAY_SECS` | `30.0` | Seconds to delay response when tarpit is enabled for a service |
| `WEBHOOK_URLS` | _(empty)_ | Comma-separated list of webhook URLs to POST alerts to |
| `WEBHOOK_RISK_LEVELS` | `CRITICAL,HIGH` | Which risk levels trigger webhook notifications |
| `WEBHOOK_FORMAT` | `json` | Webhook payload format: `slack`, `discord`, or `json` |
| `WEBHOOK_TIMEOUT_SECS` | `5.0` | Timeout for webhook HTTP requests |
| `ABUSEIPDB_API_KEY` | _(empty)_ | [AbuseIPDB](https://www.abuseipdb.com/register) API key — enables reputation checks |
| `ABUSEIPDB_MAX_AGE_DAYS` | `90` | Max report age used in AbuseIPDB queries |
| `METRICS_ENABLED` | `false` | Set to `true` to expose `/metrics` in Prometheus text format |
| `METRICS_TOKEN` | _(empty)_ | Optional Bearer token to protect the `/metrics` endpoint |
| `AUTO_BLOCK_ENABLED` | `false` | Automatically block IPs that repeatedly trigger CRITICAL alerts |
| `AUTO_BLOCK_THRESHOLD` | `3` | Number of CRITICAL hits within the window to trigger auto-block |
| `AUTO_BLOCK_WINDOW` | `300` | Time window in seconds for the auto-block threshold |

---

## Risk Classification

| Level | Colour | Triggers |
|---|---|---|
| **CRITICAL** | 🔴 | Jailbreak / prompt injection, code execution (`exec`, `os.system`, `subprocess`), path traversal, SQL injection, mass scanning (>20 req/60 s), **canary token reuse**, AWS/GCP/Azure credential exposure, SSRF attempts, template injection (`{{...}}`, `${...}`), NoSQL injection (`$where`, `$eval`), base64-encoded payloads |
| **HIGH** | 🟠 | Model management (`/api/pull`, `/api/push`, `/api/delete`), scanner user-agents (nikto, sqlmap, nmap, censys…), sensitive path segments (admin, secret, .env…), GraphQL introspection, credential stuffing |
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

## Per-Service Controls

Every simulated platform has two independent controls in the **Simulated Platforms** panel:

### Enable / Disable toggle
- **Disabled services return `404`** — the attacker sees nothing, as if the service doesn't exist
- **Requests to disabled services are still logged** — honeypot intelligence is preserved
- **State persists** — toggle states survive container/service restarts (stored in SQLite)
- **Multi-tab sync** — toggling in one browser tab updates all other open tabs via WebSocket

### Tarpit toggle (TRAP)
- When enabled, responses are delayed by `TARPIT_DELAY_SECS` (default 30 s) before being sent
- Wastes the attacker's time and resources without revealing the honeypot
- Works on any service, including disabled ones (combined: 404 after a 30 s wait)
- State persists and syncs across tabs like the enable toggle

---

## Intelligence Features

### Canary Tokens
A unique fake API key (`sk-pot-…`) is generated at startup and embedded in the `/v1/models` response. If an attacker copies this key and submits it in a subsequent request, the classifier immediately flags it as **CRITICAL** with the `canary_token_reuse` pattern.

View the current canary token in the **Intelligence** panel on the dashboard.

### Webhook Alerting
Set `WEBHOOK_URLS` to receive HTTP POST notifications when CRITICAL or HIGH events fire. Supports three payload formats:

```bash
# Slack
docker run ... -e WEBHOOK_URLS=https://hooks.slack.com/... -e WEBHOOK_FORMAT=slack ...

# Discord
docker run ... -e WEBHOOK_URLS=https://discord.com/api/webhooks/... -e WEBHOOK_FORMAT=discord ...

# Generic JSON (default)
docker run ... -e WEBHOOK_URLS=https://your-endpoint.example.com/alert ...
```

Use the **Send Test Alert** button in the dashboard to verify your webhook is working.

### Threat Report
Click **⬇ Threat Report** in the dashboard header to download a self-contained HTML report containing:
- Summary stats (total requests, unique IPs, risk breakdown)
- Top 10 attacker IPs with geo and risk data
- Top 10 attacked paths
- Top 15 flagged attack patterns
- Geographic breakdown by country

### AbuseIPDB Reputation
Set `ABUSEIPDB_API_KEY` to enrich every captured IP with community abuse scores (0–100) and Tor exit-node detection. Results are cached per-IP so the free-tier 1,000 req/day limit is rarely reached. A red dot appears on high-score IPs in the live feed, and the full score is shown in the per-IP drawer.

### Prometheus Metrics
Set `METRICS_ENABLED=true` to expose `/metrics` in standard Prometheus text format. Optionally protect it with a Bearer token via `METRICS_TOKEN`. Available metrics:

| Metric | Description |
|---|---|
| `honeypot_requests_total` | Total requests captured |
| `honeypot_requests_24h` | Requests in the last 24 hours |
| `honeypot_requests_by_risk{level}` | Count per risk level |
| `honeypot_requests_by_category{category}` | Count per category |
| `honeypot_unique_ips_total` | Unique attacker IPs seen |
| `honeypot_websocket_connections` | Active dashboard WebSocket connections |
| `honeypot_service_enabled{service}` | 1 if service is enabled, 0 if disabled |
| `honeypot_service_tarpitted{service}` | 1 if tarpit is active for the service |

### IP Blocking
Block attacker IPs directly from the dashboard:
- **Manual block** — click "Block IP" in the request modal, the IP session drawer, or type an IP into the Blocked IPs panel
- **Auto-block** — set `AUTO_BLOCK_ENABLED=true` to automatically block IPs that hit `AUTO_BLOCK_THRESHOLD` CRITICAL events within `AUTO_BLOCK_WINDOW` seconds; a toast notification fires in all open dashboard tabs
- Blocked IPs receive an instant `429 Too Many Requests` — requests are still logged so intelligence is preserved
- Unblock any IP from the Blocked IPs panel at any time

### Attack Intelligence Charts
Two new charts below the standard risk/category/timeline charts:
- **7-Day Trend** — stacked bar chart showing CRITICAL / HIGH / MEDIUM / LOW request counts per day for the last week
- **Hour-of-Day Heatmap** — 7×24 colour grid revealing which days and hours attackers are most active (darker = more requests). Refreshes every 5 minutes.

### Request Body Viewer
Click any row in the live feed to inspect the full request in a modal:
- **Request tab** — method + path, expandable headers table, prettified JSON body (raw text fallback)
- **Patterns tab** — list of all flagged attack patterns matched in this request
- **Copy as cURL** — one-click button generates a ready-to-paste `curl` command for reproducing the request in your own environment

### Request Search
Use the search box above the live feed to filter by IP address, URL path, request body content, or country — results appear within 300 ms.

### Per-IP Session View
Click any IP address in the live feed to open a slide-out panel showing the complete request history for that IP: timestamps, methods, paths, risk levels, and flagged patterns.

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
│    2. IP block gate — blocked IP? → 429 (logged)       │
│    3. Service gate — disabled service? → 404 (logged)  │
│    4. Tarpit delay (if enabled for this service)       │
│    5. Route to matching fake handler                   │
│    6. asyncio.create_task(log_request) ← never blocks  │
└───────────┬────────────────────────────────────────────┘
            │
   ┌────────▼─────────┐
   │  Logger pipeline  │
   │  ├─ Classifier    │  sync regex + canary check → (category, risk, flags)
   │  ├─ Geolocator    │  async, 2-layer cache (memory + SQLite)
   │  ├─ SQLite write  │  aiosqlite, single write lock
   │  ├─ WS broadcast  │  fan-out to all dashboard clients
   │  └─ Webhooks      │  async POST to Slack/Discord/JSON endpoints
   └────────┬──────────┘
            │ WebSocket
   ┌────────▼──────────────────────────────┐
   │  Dashboard  /__admin  (HTTP Basic Auth)│
   │  ├─ World map       Leaflet + CartoDB  │
   │  ├─ Request feed    live + search      │
   │  ├─ Request modal   body/headers/cURL  │
   │  ├─ IP session view slide-out drawer   │
   │  ├─ Charts          risk/cat/24h/7d    │
   │  ├─ Heatmap         hour-of-day grid   │
   │  ├─ Service panel   enable + tarpit    │
   │  ├─ Blocked IPs     manual + auto      │
   │  ├─ Intelligence    webhooks + canary  │
   │  └─ Threat report   HTML download      │
   └───────────────────────────────────────┘
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
