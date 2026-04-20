# AI Honeypot

A lightweight honeypot that simultaneously masquerades as **13 different AI API servers**, capturing and classifying every request on a live dashboard with a global attack map.

Designed to run on a Raspberry Pi or any Ubuntu server. Ships as a multi-architecture Docker image (`amd64` · `arm64` · `arm/v7`).

---

## Dashboard Preview

```
┌─────────────────────────────────────────────────────────────────────┐
│  🛡 AI HONEYPOT MONITOR     ⬇ Threat Report      ● LIVE             │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────────┤
│ Total    │ Last 24h │ Critical │ High     │ Medium   │ Unique IPs   │
│ 14,832   │ 1,204    │ 87       │ 342      │ 891      │ 2,341        │
├──────────────────────────────┬──────────────────────────────────────┤
│                              │ 🔍 Search    ⬇ Export CSV  [Clear]   │
│   🌍 World Map               ├──────────────────────────────────────┤
│   (risk-coloured pins)       │ Time     IP*              Risk Ctry  │
│                              │ 14:32:01 185.220.x.x C2 ANOMALY  RU  │
│                              │ 14:31:58 103.21.x.x TOR GEORISK  CN  │
│                              │  * click IP → session drawer         │
│                              │  * click row → modal  j/k/Enter/b    │
├──────────┬───────────────────┴──────────────────────────────────────┤
│ Risk Pie │ Category Bar         │ 24-Hour Timeline                  │
├──────────┴──────────────────────┴───────────────────────────────────┤
│  📈 7-Day Trend (stacked CRIT/HIGH/MED/LOW per day)                 │
│  🕐 Hour-of-Day Heatmap (7×24 grid — when do attacks peak?)         │
├─────────────────────────────────────────────────────────────────────┤
│  Simulated Platforms  (toggle to enable/disable · TRAP to tarpit)   │
│  🦙 Ollama [ON][—] 🤖 OpenAI [ON][TRAP] 🧠 Anthropic [OFF][—]       │
├─────────────────────────────────────────────────────────────────────┤
│  🔍 Intelligence                                                    │
│  Webhook Alerts: ✓ Active · 1 URL · Format: slack · CRITICAL,HIGH   │
│  Canary Token:   sk-pot-a1b2c3d4e5f6g7h8    [Copy]                  │
│  Deception URL:  http://host/track/abc123    [Copy]                 │
│  Feodo Feed:     ✓ Active · 8,234 C2 IPs   · refreshed 04:00        │
│    Detected IPs: 185.220.x.x · 103.21.x.x  (click to open drawer)   │
│  ThreatFox Feed: ✓ Active · 12,847 IOCs    · refreshed 04:00        │
├─────────────────────────────────────────────────────────────────────┤
│  🔬 IP Session Drawer (click any IP)                                │
│  IP: 185.220.101.x   Hostname: exit-node.tor-relay.example.com      │
│  ISP: Frantech Solutions   Country: Netherlands / Amsterdam         │
│  AbuseIPDB: 98/100   GreyNoise: MALICIOUS — Tor exit node           │
│  [DATACENTER] [TOR EXIT] [ThreatFox: Cobalt Strike] [C2]            │
├─────────────────────────────────────────────────────────────────────┤
│  🏆 Top Attackers                                                   │
│  Top IPs: 1. 185.220.x.x (RU) 341 req CRITICAL  2. …                │
│  Top Countries: 1. China 38.2%  2. Russia 21.1%  3. US 9.4%         │
├─────────────────────────────────────────────────────────────────────┤
│  🚫 Blocked IPs  [3]  Auto-block: on                                │
│  185.220.x.x  auto: 3 criticals in 300s   2026-04-17  [Unblock]     │
├─────────────────────────────────────────────────────────────────────┤
│  ✅ Allowed IPs  [1]  Whitelisted — never logged or blocked         │
│  192.168.1.10   my home IP   2026-04-19  [Remove]                   │
├─────────────────────────────────────────────────────────────────────┤
│  🔎 Custom Detection Rules  [2]  Operator regex patterns            │
│  "Crypto miner"  xmrig|stratum\+  CRITICAL  [ON]  [Delete]          │
│  Name / Pattern / Risk ▾               [Add Rule]                   │
├─────────────────────────────────────────────────────────────────────┤
│  🤖 ML Intelligence  (collapsible)                                  │
│  Model Status:  ✓ Trained · 2,341 samples · last: 2026-04-19 14:00  │
│    Composite baseline: p10=0.08 · p50=0.21 · p90=0.54               │
│  Anomaly Detection:  12 anomalies in last 24h  (Isolation Forest)   │
│  Bot Detection:      8 high-confidence bots ≥80%  (Random Forest)   │
│  Attack Clusters:    3 active clusters  (DBSCAN)                    │
│    Cluster 0: 12 IPs · CRITICAL   Cluster 1: 7 IPs · HIGH           │
│  🌍 Geo Risk: CN 89% · RU 76% · IR 71% · KP 68% · BR 55%            │
│    Top ASNs: AS4134 91% · AS1234 78%                                │
├─────────────────────────────────────────────────────────────────────┤
│  ABOUT ▾  (collapsible — built by Ozzytech · Martyn Oswald)         │
└─────────────────────────────────────────────────────────────────────┘
● = high AbuseIPDB score · C2 = Feodo botnet · TF = ThreatFox IOC · 📝 = note · ANOMALY/BOT/GEORISK/ML:BAND = ML flags
```

---

## Features

- **13 fake AI platform APIs** — each responds convincingly on the same port
- **Streaming responses** — word-by-word token streaming at realistic GPU speed (~25 tok/s)
- **Risk classification** — CRITICAL / HIGH / MEDIUM / LOW with 40+ attack patterns
- **Enhanced threat detection** — AWS/GCP/Azure credential exposure, SSRF, template injection, NoSQL injection, GraphQL introspection, base64-encoded payloads, credential stuffing
- **Custom detection rules** — define your own regex patterns via the dashboard UI; assigned to any risk level; hot-reloaded instantly, no restart needed
- **Threat feed integration** — [Feodo Tracker](https://feodotracker.abuse.ch/) C2 blocklist downloaded at startup and refreshed every 24 h; matched IPs get a `C2` badge in the live feed
- **Deception tokens** — a trackable URL is shown in the Intelligence panel; embed it in fake model responses; any attacker who follows it fires a CRITICAL `deception_callback` alert
- **Email alerts** — SMTP (stdlib, no extra deps) sends HTML alerts for CRITICAL/HIGH events; configure with `SMTP_HOST`, `SMTP_TO`, etc.
- **Scheduled reports** — daily or weekly HTML threat report emailed automatically (`REPORT_SCHEDULE=daily|weekly`)
- **SIEM / syslog forwarding** — fire-and-forget UDP syslog in JSON or CEF format to any log aggregator (`SYSLOG_HOST`, `SYSLOG_FORMAT=json|cef`)
- **Data retention** — automatic hourly purge of requests older than `MAX_REQUEST_AGE_DAYS` days (0 = keep forever)
- **Fail2ban / iptables export** — blocked IPs written to `BLOCKLIST_FILE` in plain or fail2ban format on every block/unblock
- **IP blocking** — manual block from dashboard/modal/drawer, or auto-block IPs that repeatedly trigger CRITICAL alerts
- **IP allow-list** — whitelist your own IPs so they never appear in the feed or trigger auto-block
- **IP notes / tagging** — annotate any attacker IP with a freeform note; appears in the session drawer and live feed (📝 tooltip)
- **CSV export** — one-click download of all (or filtered) requests as CSV; supports `?risk=`, `?category=`, `?ip=`, `?since=` filters
- **ISP & datacenter detection** — ISP name and datacenter/hosting flag extracted from ip-api.com (free tier, no extra key); shown in the IP session drawer
- **Reverse DNS** — PTR hostname lookup for every attacker IP; cached and displayed in the session drawer (e.g. `exit-node.tor.example.com`)
- **ThreatFox feed** — [abuse.ch](https://threatfox.abuse.ch/) malware C2 IOC feed (no API key, refreshes every 24 h); IPs matched against known botnet infrastructure with the malware family name shown as a badge
- **GreyNoise integration** — community API classifies IPs as mass internet scanner noise vs targeted attack; `RIOT` flag identifies known-benign infrastructure (Googlebot, Shodan, etc.); requires free `GREYNOISE_API_KEY`
- **Top Attackers leaderboard** — Top 10 IPs and Top 10 countries ranked by request count, updated on every stats refresh
- **Keyboard navigation** — `j`/`k` navigate feed rows, `Enter` opens request modal, `b` blocks the selected IP, `Escape` closes modals
- **Per-service toggle** — enable or disable any platform from the dashboard; changes take effect instantly and persist across restarts
- **Tarpit mode** — per-service delay (default 30 s) that wastes attacker time before responding
- **Canary tokens** — fake API key embedded in `/v1/models`; any attacker who reuses it is instantly flagged CRITICAL
- **Webhook alerting** — HTTP POST to Slack, Discord, or generic JSON endpoints on CRITICAL/HIGH events
- **AbuseIPDB integration** — reputation score and Tor detection for every attacker IP (optional)
- **IP geolocation** — country, city and coordinates via ip-api.com (2-layer cache)
- **Live dashboard** — world map with risk-coloured pins, request feed, charts, timeline
- **Attack intelligence charts** — 7-day trend chart and hour-of-day heatmap showing when attacks peak
- **Real-time WebSocket push** — authenticated WebSocket (`?token=sha256(ADMIN_PASSWORD)`) delivers live updates without polling
- **Request body viewer** — click any feed row to inspect headers, prettified JSON body, and flagged patterns; copy as cURL in one click
- **Request search** — full-text search across IP, path, body, and country in the feed
- **Per-IP session view** — click any IP to open a slide-out drawer with its complete request timeline
- **Threat report** — one-click self-contained HTML download with top IPs, paths, patterns, and geo breakdown
- **Prometheus metrics** — optional `/metrics` endpoint for Grafana / alertmanager integration
- **TinyML on-device intelligence** — 5 on-device models (Isolation Forest, DBSCAN, 2× Random Forest, GeoRisk) run entirely in-process; ip_cache enrichment features, timing regularity, Bayesian geo risk, and composite threat scoring; no cloud, no GPU; Raspberry Pi compatible (~120 MB RAM overhead)
- **Multi-arch Docker image** — `linux/amd64`, `linux/arm64`, `linux/arm/v7`
- **Lightweight** — single async worker, SQLite only, <512 MB RAM on Raspberry Pi 4

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

### Core

| Variable | Default | Description |
|---|---|---|
| `PORT` | `11434` | Listen port — matches real Ollama for honeypot effect |
| `ADMIN_USERNAME` | `admin` | Dashboard login username |
| `ADMIN_PASSWORD` | `changeme` | **Change this before deploying** |
| `ADMIN_PREFIX` | `/__admin` | Dashboard URL prefix |
| `DB_PATH` | `honeypot.db` | SQLite path (`/data/honeypot.db` in Docker) |
| `MAX_REQUESTS_STORED` | `100000` | SQLite row cap (oldest rows pruned) |
| `MAX_REQUEST_AGE_DAYS` | `0` | Auto-purge requests older than N days (0 = disabled) |
| `STREAM_WORD_DELAY_SECS` | `0.04` | Per-word delay in fake streaming (~25 tok/s) |

### Detection thresholds

| Variable | Default | Description |
|---|---|---|
| `RAPID_REQUEST_THRESHOLD` | `20` | Requests/60 s from one IP → CRITICAL |
| `REPEAT_IP_THRESHOLD` | `5` | Requests/10 min from one IP → MEDIUM |
| `LARGE_BODY_THRESHOLD` | `5000` | Body bytes above this → MEDIUM |

### Geolocation

| Variable | Default | Description |
|---|---|---|
| `GEO_CACHE_TTL_HOURS` | `24` | IP geolocation cache lifetime |

### Blocking & tarpit

| Variable | Default | Description |
|---|---|---|
| `TARPIT_DELAY_SECS` | `30.0` | Seconds to delay response when tarpit is enabled |
| `AUTO_BLOCK_ENABLED` | `false` | Automatically block IPs that repeatedly trigger CRITICAL alerts |
| `AUTO_BLOCK_THRESHOLD` | `3` | Number of CRITICAL hits within the window to trigger auto-block |
| `AUTO_BLOCK_WINDOW` | `300` | Time window in seconds for the auto-block threshold |
| `BLOCKLIST_FILE` | _(empty)_ | Path to write blocked IPs for fail2ban / iptables (plain or fail2ban format) |
| `BLOCKLIST_FORMAT` | `plain` | `plain` (one IP per line) or `fail2ban` |

### Alerting

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_URLS` | _(empty)_ | Comma-separated list of webhook URLs to POST alerts to |
| `WEBHOOK_RISK_LEVELS` | `CRITICAL,HIGH` | Which risk levels trigger webhook notifications |
| `WEBHOOK_FORMAT` | `json` | Webhook payload format: `slack`, `discord`, or `json` |
| `WEBHOOK_TIMEOUT_SECS` | `5.0` | Timeout for webhook HTTP requests |
| `SMTP_HOST` | _(empty)_ | SMTP server hostname — enables email alerts when set |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | _(empty)_ | SMTP username |
| `SMTP_PASS` | _(empty)_ | SMTP password |
| `SMTP_FROM` | `honeypot@localhost` | From address for alert emails |
| `SMTP_TO` | _(empty)_ | Recipient address for alert emails |
| `SMTP_TLS` | `true` | Use STARTTLS (`true`) or SSL (`false`) |
| `EMAIL_RISK_LEVELS` | `CRITICAL` | Which risk levels trigger email alerts |
| `REPORT_SCHEDULE` | _(empty)_ | `daily` or `weekly` — enables scheduled HTML threat reports |
| `REPORT_EMAIL_TO` | _(empty)_ | Recipient for scheduled reports (defaults to `SMTP_TO`) |

### SIEM / syslog

| Variable | Default | Description |
|---|---|---|
| `SYSLOG_HOST` | _(empty)_ | Syslog receiver hostname — enables forwarding when set |
| `SYSLOG_PORT` | `514` | UDP port |
| `SYSLOG_FORMAT` | `json` | Payload format: `json` or `cef` (Common Event Format) |

### Integrations

| Variable | Default | Description |
|---|---|---|
| `ABUSEIPDB_API_KEY` | _(empty)_ | [AbuseIPDB](https://www.abuseipdb.com/register) API key — enables reputation checks |
| `ABUSEIPDB_MAX_AGE_DAYS` | `90` | Max report age used in AbuseIPDB queries |
| `GREYNOISE_API_KEY` | _(empty)_ | [GreyNoise](https://www.greynoise.io/) community API key — classifies IPs as noise/malicious/benign |
| `METRICS_ENABLED` | `false` | Set to `true` to expose `/metrics` in Prometheus text format |
| `METRICS_TOKEN` | _(empty)_ | Optional Bearer token to protect the `/metrics` endpoint |
| `DECEPTION_ENABLED` | `true` | Generate deception token URL shown in Intelligence panel |

> **WebSocket auth token** is derived automatically as `sha256(ADMIN_PASSWORD)` — no separate variable needed. Change `ADMIN_PASSWORD` and the token rotates with it.

---

## Risk Classification

| Level | Colour | Triggers |
|---|---|---|
| **CRITICAL** | 🔴 | Jailbreak / prompt injection, code execution (`exec`, `os.system`, `subprocess`), path traversal, SQL injection, mass scanning (>20 req/60 s), **canary token reuse**, **deception callback**, **custom CRITICAL rule match**, AWS/GCP/Azure credential exposure, SSRF attempts, template injection (`{{...}}`, `${...}`), NoSQL injection (`$where`, `$eval`), base64-encoded payloads |
| **HIGH** | 🟠 | Model management (`/api/pull`, `/api/push`, `/api/delete`), scanner user-agents (nikto, sqlmap, nmap, censys…), sensitive path segments (admin, secret, .env…), GraphQL introspection, credential stuffing, **custom HIGH rule match** |
| **MEDIUM** | 🟡 | Embeddings & reranking, image generation, audio transcription, repeated IPs (>5/10 min), unknown model names, large bodies (>5 KB), **custom MEDIUM rule match** |
| **LOW** | 🟢 | Normal inference, chat, model listing, enumeration, **custom LOW rule match** |

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

### Custom Detection Rules
Define your own regex patterns from the **🔎 Custom Detection Rules** panel:
- Enter a name, regex pattern, and risk level (CRITICAL / HIGH / MEDIUM / LOW)
- Rules are compiled and hot-reloaded instantly — no restart required
- Enable or disable individual rules without deleting them
- Matched rules add a `custom:<flag_name>` tag to the request's flagged patterns
- Patterns are tested against the full request body + headers text

### Threat Feed Integration
The honeypot downloads the [Feodo Tracker](https://feodotracker.abuse.ch/) recommended C2 IP blocklist at startup and refreshes it every 24 hours (no API key required):
- IPs matching known C2 infrastructure get a red **C2** badge in the live feed
- Feed statistics (IP count, last refresh time) are shown in the Intelligence panel
- **Detected C2 IPs table** — any attacker IP that matched the feed is listed directly in the Intelligence panel with hit count, country, last seen timestamp, and max risk level; click any IP to open its session drawer
- The lookup is synchronous and in-memory — zero overhead on the hot path

### Deception Tokens
A unique session-scoped tracking URL is generated at startup and displayed in the **Intelligence** panel:
- Copy the URL and embed it anywhere in your fake model responses (e.g. as a "documentation link")
- Any attacker who follows the URL triggers a CRITICAL `deception_callback` alert
- The `/track/{token}` endpoint returns a silent 1×1 transparent GIF so the request completes normally
- All callbacks are logged to a dedicated `deception_callbacks` SQLite table

### Email Alerts
Set `SMTP_HOST` and `SMTP_TO` to receive HTML email alerts for high-severity events:

```bash
docker run ... \
  -e SMTP_HOST=smtp.gmail.com \
  -e SMTP_PORT=587 \
  -e SMTP_USER=you@gmail.com \
  -e SMTP_PASS=app-password \
  -e SMTP_TO=alerts@example.com \
  -e EMAIL_RISK_LEVELS=CRITICAL \
  ...
```

Uses Python's stdlib `smtplib` — no extra dependencies. Runs in an executor so alerts never block request handling.

### Scheduled Threat Reports
Set `REPORT_SCHEDULE=daily` or `REPORT_SCHEDULE=weekly` to receive automated HTML threat reports by email:
- Sent at the first scheduled hour after midnight (daily) or on Monday (weekly)
- Contains the same content as the **⬇ Threat Report** HTML download: top IPs, paths, patterns, geo breakdown
- Requires `SMTP_HOST` and either `REPORT_EMAIL_TO` or `SMTP_TO`

### SIEM / Syslog Forwarding
Set `SYSLOG_HOST` to forward every captured event to your log aggregator via UDP:

```bash
# JSON format (default)
docker run ... -e SYSLOG_HOST=192.168.1.100 -e SYSLOG_PORT=514 ...

# CEF (Common Event Format) — for Splunk, IBM QRadar, etc.
docker run ... -e SYSLOG_HOST=192.168.1.100 -e SYSLOG_FORMAT=cef ...
```

### Data Retention
Set `MAX_REQUEST_AGE_DAYS` to automatically purge old requests:
- An hourly background task deletes rows older than the configured limit
- Set to `0` (default) to keep all data indefinitely
- Works alongside `MAX_REQUESTS_STORED` (hard cap on total row count)

### Fail2ban / iptables Integration
Set `BLOCKLIST_FILE` to write blocked IPs to a file on every block/unblock event:

```bash
# Plain format — one IP per line
docker run ... -e BLOCKLIST_FILE=/data/blocked.txt ...

# fail2ban format — with timestamps and reason comments
docker run ... -e BLOCKLIST_FILE=/data/blocked.txt -e BLOCKLIST_FORMAT=fail2ban ...
```

Mount the file into your host and configure fail2ban to read it, or use it directly with `iptables`.

### ISP & Datacenter Detection
The ip-api.com free tier returns the ISP name and a `hosting` flag for every attacker IP. Both are shown in the IP session drawer:
- **ISP** — carrier or hosting provider name (e.g. "DigitalOcean", "Alibaba Cloud", "Deutsche Telekom")
- **DATACENTER badge** — shown when the IP belongs to a hosting or cloud provider rather than a residential ISP

No API key required; extracted alongside standard geolocation data.

### Reverse DNS
A PTR record lookup (`gethostbyaddr`) is performed for every new public IP and cached alongside geo data. The hostname appears in the session drawer — `exit-node.tor.example.com`, `scan.example-security.com`, etc. — often revealing the attacker's infrastructure at a glance.

### ThreatFox Feed Integration
The honeypot downloads the [ThreatFox](https://threatfox.abuse.ch/) IP:port IOC feed at startup and refreshes it every 24 hours (no API key required):
- IPs matching known malware C2 infrastructure get a red **ThreatFox** badge in the session drawer showing the malware family (e.g. "Cobalt Strike", "Mirai", "AsyncRAT")
- Feed statistics (IOC count, last refresh time) are logged at startup
- The lookup is synchronous and in-memory — zero overhead on the hot path

### GreyNoise Classification
Set `GREYNOISE_API_KEY` to classify every attacker IP via the [GreyNoise](https://www.greynoise.io/) community API:
- **MALICIOUS** — targeted attacker, not mass-internet noise
- **BENIGN** — known safe infrastructure (Googlebot, Shodan, Censys, academic scanners)
- **RIOT** badge — IP belongs to known benign internet infrastructure; safe to deprioritise
- **noise** flag — IP is a mass scanner generating background internet noise vs a targeted attacker

Results are cached in `ip_cache` and shown in the session drawer. Free community tier covers 1,000 checks/day.

### TinyML On-Device Intelligence
Five on-device models run entirely in-process — no cloud API, no GPU, no separate service. All inference happens in microseconds per request. Designed to run alongside the honeypot on a Raspberry Pi 4.

#### Models

| Model | Algorithm | What it detects |
|---|---|---|
| **Anomaly Detection** | Isolation Forest | Requests that look unusual compared to your baseline traffic — catches novel attacks not covered by regex rules |
| **Attack Clustering** | DBSCAN | Groups attacker IPs by behavioural fingerprint — spot coordinated campaigns where multiple IPs run the same scanner |
| **Risk Enhancement** | Random Forest | Continuous 0–1 probability trained on your historical `risk_level` labels — catches misclassified requests |
| **Bot Detection** | Random Forest | Scores sessions as automated vs human based on timing regularity, path diversity, and user-agent consistency |
| **Geo Risk** | Bayesian dict | Country and ASN risk scores derived from historical high/critical ratios — catches new IPs from known-bad origins before they accumulate session history |

#### Feature vectors
Features are enriched with ip_cache reputation data at training and inference time:

**Per-request (15 features):** body length, path length, path depth, header count, hour of day, POST flag, JSON body flag, auth header flag, flagged pattern count, category, C2 flag, AbuseIPDB score, Tor flag, hosting flag, ThreatFox hit

**Per-session (15 features):** total requests, unique paths, unique user-agents, avg inter-request time, session span, high/critical risk ratio, unique categories, path diversity ratio, avg body size, AbuseIPDB score, Tor flag, hosting flag, ThreatFox hit, **timing std dev** (inter-request gap standard deviation — the canonical bot-detection signal; low variance + high request count = scanner)

#### Composite threat score
Every request receives a `ml_composite_score` (0–1) combining all sub-models:

| Signal | Weight |
|---|---|
| Anomaly score (Isolation Forest) | 25% |
| Risk probability (Random Forest) | 35% |
| Geo risk (Bayesian country/ASN) | 20% |

Mapped to `ml_threat_band`: **LOW** / **MEDIUM** / **HIGH** / **CRITICAL**. The ML Intelligence status card shows the training-data `p10 / p50 / p90` percentile calibration so you can judge whether thresholds are appropriate for your traffic.

#### Dashboard
The collapsible **🤖 ML Intelligence** panel shows five cards:
- **Model status** — trained / warming up / sample count / last training time / composite percentile calibration
- **Anomaly detection** — real count of requests flagged anomalous in the last 24 h (computed from training data, not a placeholder)
- **Bot detection** — real count of high-confidence bot sessions (≥ 80%) detected at last training
- **Attack clusters** — active DBSCAN cluster count with per-cluster IP counts
- **🌍 Geo Risk Intelligence** — top-5 riskiest countries and ASNs ranked by Bayesian risk score

#### Feed badges

| Badge | Colour | Condition |
|---|---|---|
| **ANOMALY** | purple | request anomaly score ≥ 0.75 |
| **BOT** | blue | session bot probability ≥ 80% |
| **GEORISK** | amber | geo risk score ≥ 0.70 (shown only when ANOMALY badge is absent) |
| **ML:HIGH** | orange | composite threat score ≥ 0.50 |
| **ML:CRITICAL** | red | composite threat score ≥ 0.75 |

#### Training schedule
- **Cold start**: models are `None` — all scores return `None` gracefully, no errors
- **First train**: triggered automatically when 100+ requests exist in the database
- **Retrain**: every 200 new requests or every 60 minutes, whichever comes first
- **Runs in**: a thread executor — never blocks the async event loop
- **Model version guard**: if serialised models have the wrong feature dimension (e.g. from a pre-Phase-2 install), they are discarded and retrained automatically

#### Raspberry Pi sizing
| Component | RAM | CPU time (Pi 4) |
|---|---|---|
| scikit-learn import | ~80 MB | 2 s startup |
| All 5 models loaded | ~40 MB | — |
| GeoRisk dicts (Phase 2) | < 1 MB | — |
| Per-request inference | negligible | < 1 ms |
| Training (1,000 samples) | ~50 MB peak | ~5 s |

Models are saved to `/data/ml_models/` via joblib and reloaded on restart. Total overhead: ~121 MB RAM, ~2 s extra startup.

API: `GET /__admin/api/ml/stats` — returns model status, real training counters, cluster summary, top risky countries/ASNs, and composite percentile calibration.

### Top Attackers Leaderboard
The **🏆 Top Attackers** section below the intelligence charts shows:
- **Top IPs** — the 10 most active attacker IPs with country, request count, and max risk level; click any IP to open its session drawer
- **Top Countries** — the 10 most active source countries with request counts and percentage of total traffic

Updated automatically with every stats refresh (every 30 seconds).

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

### IP Allow-list
Prevent your own IPs from polluting the feed:
- Add IPs (with an optional label) via the **✅ Allowed IPs** panel in the dashboard
- Allowed IPs pass straight through the ASGI middleware — no logging, no geolocation, no auto-block
- Persisted in SQLite and loaded into an in-memory set at startup for zero-overhead checks

### IP Notes / Tagging
Annotate attacker IPs with operator context:
- Open any IP's session drawer → click the note area to add or edit a free-text note
- Notes appear as a 📝 tooltip on the IP in the live feed, in the session drawer, and in the request modal
- Notes survive restarts (stored in `ip_notes` SQLite table, cached in memory)
- Delete a note by saving an empty string

### CSV Export
Export request data for offline analysis (Excel, Splunk, pandas, SIEM):
- Click **⬇ Export CSV** in the feed panel header for a full download
- Supports query filters: `?risk=CRITICAL`, `?category=attack`, `?ip=1.2.3.4`, `?since=2024-01-01`, `?limit=50000`
- Columns: `id`, `timestamp`, `ip`, `method`, `path`, `category`, `risk_level`, `country`, `city`, `user_agent`, `flagged_patterns`, `body_snippet` (first 200 chars)
- Streamed in batches — safe to export large datasets without memory spikes

### Keyboard Navigation
Navigate the live feed without touching the mouse:

| Key | Action |
|---|---|
| `j` / `↓` | Select next row in feed |
| `k` / `↑` | Select previous row in feed |
| `Enter` | Open request modal for selected row |
| `b` | Block IP of selected row |
| `Escape` | Close modal or drawer |

### WebSocket Security
The real-time `/ws` endpoint is token-authenticated:
- A `sha256(ADMIN_PASSWORD)` token is injected into the dashboard page at load time
- The browser appends `?token=<hash>` to the WebSocket URL automatically
- Connections without a valid token are closed immediately with WebSocket code 1008 (Policy Violation)
- Rotating `ADMIN_PASSWORD` instantly invalidates any existing unauthorised connections

### Attack Intelligence Charts
Two charts below the standard risk/category/timeline charts:
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
┌────────────────────────────────────────────────────────────┐
│  FastAPI Middleware (_CaptureMiddleware)                    │
│    1. Read body                                            │
│    2. Allow-list gate — whitelisted IP? → pass (no log)    │
│    3. IP block gate  — blocked IP? → 429 (still logged)    │
│    4. Service gate   — disabled service? → 404 (logged)    │
│    5. Tarpit delay   — if enabled for this service         │
│    6. Route to matching fake handler                       │
│    7. asyncio.create_task(log_request) ← never blocks      │
└───────────┬────────────────────────────────────────────────┘
            │
   ┌────────▼──────────────┐
   │  Logger pipeline       │
   │  ├─ Classifier         │  sync regex + canary + custom rules
   │  ├─ Geolocator         │  async, 2-layer cache (memory + SQLite)
   │  ├─ Reverse DNS        │  async PTR lookup in thread executor (cached)
   │  ├─ AbuseIPDB          │  optional reputation check (cached)
   │  ├─ GreyNoise          │  optional noise/malicious classification (cached)
   │  ├─ Threat feeds       │  sync C2 lookup (Feodo Tracker + ThreatFox)
   │  ├─ ML engine          │  anomaly score + bot probability (scikit-learn)
   │  ├─ IP notes           │  attach operator note to broadcast
   │  ├─ Auto-block         │  CRITICAL threshold check → block + broadcast
   │  ├─ SQLite write       │  aiosqlite, single write lock
   │  ├─ WS broadcast       │  fan-out to authenticated dashboard clients
   │  ├─ Webhooks           │  async POST to Slack/Discord/JSON
   │  ├─ Email alerts       │  SMTP in executor (non-blocking)
   │  ├─ Syslog             │  UDP JSON/CEF fire-and-forget
   │  └─ Deception log      │  /track/ callbacks → deception_callbacks table
   └────────┬───────────────┘
            │ WebSocket (token-authenticated)
   ┌────────▼────────────────────────────────────────┐
   │  Dashboard  /__admin  (HTTP Basic Auth)          │
   │  ├─ World map           Leaflet + CartoDB        │
   │  ├─ Request feed        live + search + CSV ⬇   │
   │  ├─ Request modal       body/headers/cURL        │
   │  ├─ IP session view     drawer + note editor     │
   │  ├─ Charts              risk/cat/24h/7d/heatmap  │
   │  ├─ Service panel       enable + tarpit          │
   │  ├─ Intelligence        webhooks/canary/deception│
   │  ├─ Threat feed stats   C2 count + last refresh  │
   │  ├─ Top Attackers       IPs + countries leaderboard│
   │  ├─ Blocked IPs         manual + auto-block      │
   │  ├─ Allowed IPs         whitelist panel          │
   │  ├─ Custom Rules        regex CRUD + hot-reload  │
   │  ├─ ML Intelligence     anomaly/bot/cluster panel│
   │  └─ Threat report       HTML download            │
   └─────────────────────────────────────────────────┘

Background tasks (asyncio):
   ├─ Feodo Tracker feed refresh  (every 24 h)
   ├─ ThreatFox IOC feed refresh  (every 24 h)
   ├─ ML model training loop      (every 200 req or 60 min)
   ├─ Data retention purge        (every 1 h)
   └─ Scheduled threat report     (daily / weekly)
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

---

## About

AI Honeypot is a lightweight, high-fidelity deception platform built to catch automated scanners, credential harvesters, and targeted attackers probing for exposed AI infrastructure. It impersonates 13 real AI API servers simultaneously — Ollama, OpenAI, Anthropic, HuggingFace, Stable Diffusion, and more — on a single port, capturing and classifying every request in real time.

The project grew out of a curiosity about what actually hits an exposed AI endpoint on the internet. The answer turned out to be a lot: credential stuffers, botnet C2 callbacks, jailbreak attempts, prompt injection, mass scanners, and researchers — all within hours of a port being opened.

Everything runs on a Raspberry Pi with no cloud dependencies. A single async worker, SQLite, and about 384 MB of RAM is all it takes.

### Author

**Martyn Oswald** — [0zzy-tech](https://github.com/0zzy-tech)

Built and maintained as an open-source security research tool. Contributions, issues, and ideas welcome.
