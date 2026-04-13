# AI Honeypot

A lightweight honeypot that masquerades as an [Ollama](https://ollama.com) AI server,
capturing and classifying every request with a live web dashboard.

---

## Features

- **Convincing fake Ollama API** — responds to all standard endpoints on port 11434
- **OpenAI-compatible layer** — `/v1/chat/completions`, `/v1/models`, `/v1/embeddings`, etc.
- **Streaming responses** — word-by-word NDJSON at realistic speed (~25 tokens/sec)
- **Risk classification** — CRITICAL / HIGH / MEDIUM / LOW with pattern matching for jailbreaks, code execution, SQL injection, mass scanning
- **IP geolocation** — country + city + coordinates via ip-api.com (2-layer cache, respects free-tier limits)
- **Live dashboard** — world map, request feed, risk pie chart, category bar chart, 24h timeline
- **Real-time updates** — WebSocket push to dashboard on every request
- **Lightweight** — single async worker, SQLite, <256 MB RAM on Raspberry Pi 4

---

## Quick Start (Raspberry Pi / Ubuntu)

```bash
git clone <repo-url> ai-honeypot
cd ai-honeypot

# Edit credentials BEFORE installing
nano config.py   # Change ADMIN_PASSWORD

sudo ./setup.sh
sudo systemctl start ai-honeypot
```

Then open `http://<your-pi-ip>:11434/__admin` in a browser.

---

## Manual Run (development)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Dashboard: `http://localhost:11434/__admin`  
Default login: `admin` / `changeme`

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `PORT` | `11434` | Ollama default port |
| `ADMIN_PASSWORD` | `changeme` | Dashboard HTTP Basic Auth |
| `ADMIN_PREFIX` | `/__admin` | Dashboard URL prefix |
| `RAPID_REQUEST_THRESHOLD` | `20` | Requests/60s → CRITICAL |
| `STREAM_WORD_DELAY_SECS` | `0.04` | Token stream speed |
| `MAX_REQUESTS_STORED` | `100000` | SQLite row limit |

---

## Risk Levels

| Level | Triggers |
|---|---|
| **CRITICAL** | Jailbreak attempts, prompt injection, code execution patterns, SQL injection, mass scanning (>20 req/60s) |
| **HIGH** | Model management endpoints (`/api/pull`, `/api/push`, `/api/delete`), scanner user-agents, sensitive path segments |
| **MEDIUM** | Embeddings, repeated requests (>5/10min), unknown model names, large bodies |
| **LOW** | Normal inference / chat / model listing |

---

## Request Categories

`inference` · `model_management` · `embeddings` · `enumeration` · `model_info` · `openai_compat` · `scanning` · `attack`

---

## Service Management

```bash
sudo systemctl start   ai-honeypot
sudo systemctl stop    ai-honeypot
sudo systemctl restart ai-honeypot
sudo journalctl -u ai-honeypot -f   # live logs
```

---

## Architecture

```
Attacker → Port 11434 (fake Ollama/OpenAI API)
                ↓
         FastAPI middleware  (captures ALL requests, incl. unknown paths)
                ↓  (asyncio.create_task — never delays response)
         Logger pipeline:
           ├── Classifier  (sync pattern matching → risk + category)
           ├── Geolocator  (async, 2-layer cache → country/city/lat/lng)
           ├── SQLite       (aiosqlite, single write lock)
           └── WebSocket broadcaster → live dashboard
```
