# Contributing to AI Honeypot

Thank you for helping make this project better. Contributions of all kinds are welcome — bug reports, new platform simulations, detection improvements, and documentation fixes.

---

## Getting Started

```bash
git clone https://github.com/0zzy-tech/Ai-pot
cd Ai-pot

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python main.py
# Dashboard: http://localhost:11434/__admin   (admin / changeme)
```

---

## Ways to Contribute

### Bug Reports
Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md). Include:
- Python version and OS
- Docker or bare metal
- Steps to reproduce
- What you expected vs. what happened

### Feature Requests
Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

### Pull Requests
1. Fork the repo and create a branch: `git checkout -b feature/your-feature`
2. Make your changes (see guides below)
3. Verify syntax: `python3 -m py_compile $(find . -name "*.py" -not -path "./.venv/*")`
4. Open a PR against `main` with a clear description of what changed and why

---

## Adding a New AI Platform Simulation

The most common contribution. Takes about 30–60 minutes for a complete platform.

### 1. Create the route file

Copy an existing platform as a template (e.g. `app/routes/llamacpp.py` for a simple one, `app/routes/ollama.py` for a complex one).

```python
# app/routes/myplatform.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/myplatform/health")
async def health():
    return JSONResponse({"status": "ok"})

@router.post("/myplatform/generate")
async def generate(req: dict):
    # Return a realistic fake response
    return JSONResponse({"text": "Hello from myplatform"})
```

### 2. Register the service

Add an entry to `SERVICES` in `app/service_registry.py`:

```python
"myplatform": {
    "label":       "My Platform",
    "description": "Brief description of what this platform is",
    "icon":        "🔧",
    "port":        8080,
    "prefixes":    ["/myplatform/"],   # path prefixes owned by this service
    "exact":       [],                  # exact paths (if any)
},
```

### 3. Register the router in main.py

```python
from app.routes import myplatform
# ...
app.include_router(myplatform.router)
```

### 4. Add known paths to the classifier

In `app/classifier.py`, add your endpoints to `KNOWN_PATHS` so they don't incorrectly trigger MEDIUM risk:

```python
"/myplatform/health", "/myplatform/generate",
```

### 5. Add a fake response (optional but recommended)

If the platform streams responses, add a generator in `app/fake_responses/generate.py`. If it uses a model catalog, reference `app/fake_responses/models_catalog.py`.

---

## Adding Attack Detection Patterns

Detection logic lives in `app/classifier.py`. To add a new CRITICAL pattern:

```python
# In the JAILBREAK_PATTERNS or CODE_EXEC_PATTERNS list:
re.compile(r"your pattern here", re.IGNORECASE),
```

Patterns are checked against the full request body text. Keep them specific enough to avoid false positives on legitimate inference traffic.

---

## Project Structure

```
app/
  classifier.py       — Risk classification (CRITICAL/HIGH/MEDIUM/LOW)
  database.py         — SQLite async layer
  geolocator.py       — IP geolocation with 2-layer cache
  abuseipdb.py        — IP reputation via AbuseIPDB API
  canary.py           — Canary token generation and detection
  webhooks.py         — Webhook alerting (Slack/Discord/JSON)
  logger.py           — Central async logging pipeline
  broadcaster.py      — WebSocket fan-out
  service_registry.py — Service enable/disable/tarpit state
  fake_responses/     — Canned responses for each platform type
  routes/
    dashboard.py      — Admin dashboard API endpoints
    metrics.py        — Prometheus metrics endpoint
    ollama.py         — Ollama native API simulation
    openai_compat.py  — OpenAI-compatible API
    vllm.py           — vLLM-specific endpoints
    lmstudio.py       — LM Studio native API
    ... (one file per platform)
config.py             — All env-var configuration
main.py               — FastAPI app, ASGI middleware, router registration
templates/            — Jinja2 HTML templates
static/               — CSS, JS
```

---

## Code Style

- Follow the existing patterns in each file
- Keep route handlers thin — business logic belongs in `app/` modules
- No new dependencies without discussion — the goal is to keep the Docker image small
- Test your changes by sending real requests to the honeypot and checking the dashboard

---

## Licence

By contributing you agree that your contributions will be licensed under the [MIT Licence](LICENSE).
