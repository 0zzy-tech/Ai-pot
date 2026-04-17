"""
Prometheus metrics endpoint.

Disabled by default — enable with METRICS_ENABLED=true.
Optionally protect with METRICS_TOKEN (Bearer token).

Scrape config example:
  - job_name: ai_honeypot
    static_configs:
      - targets: ['honeypot-host:11434']
    metrics_path: /metrics
    bearer_token: your_token_here   # if METRICS_TOKEN is set
"""

import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app import service_registry
from app.broadcaster import manager
from app.database import get_stats
from config import Config

logger = logging.getLogger(__name__)
router = APIRouter()

_START_TIME = time.time()


def _gauge(name: str, help_text: str, value: float, labels: dict | None = None) -> str:
    label_str = ""
    if labels:
        pairs = ",".join(f'{k}="{v}"' for k, v in labels.items())
        label_str = f"{{{pairs}}}"
    return f"# HELP {name} {help_text}\n# TYPE {name} gauge\n{name}{label_str} {value}\n"


def _counter(name: str, help_text: str, value: float, labels: dict | None = None) -> str:
    label_str = ""
    if labels:
        pairs = ",".join(f'{k}="{v}"' for k, v in labels.items())
        label_str = f"{{{pairs}}}"
    return f"# HELP {name} {help_text}\n# TYPE {name} counter\n{name}{label_str} {value}\n"


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(request: Request):
    # Optional Bearer token auth
    if Config.METRICS_TOKEN:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {Config.METRICS_TOKEN}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    stats = await get_stats()
    by_risk     = stats.get("by_risk", {})
    by_category = stats.get("by_category", {})
    services    = service_registry.get_all_service_states()

    lines: list[str] = []

    # ── Totals ──────────────────────────────────────────────────────────────────
    lines.append(_counter(
        "honeypot_requests_total",
        "Total HTTP requests captured by the honeypot",
        stats.get("total", 0),
    ))
    lines.append(_gauge(
        "honeypot_requests_24h",
        "Requests captured in the last 24 hours",
        stats.get("last_24h", 0),
    ))
    lines.append(_gauge(
        "honeypot_unique_ips_total",
        "Number of unique attacker IP addresses seen",
        stats.get("unique_ips", 0),
    ))
    lines.append(_gauge(
        "honeypot_uptime_seconds",
        "Seconds since the honeypot process started",
        time.time() - _START_TIME,
    ))
    lines.append(_gauge(
        "honeypot_websocket_connections",
        "Number of active WebSocket dashboard connections",
        len(manager.active_connections),
    ))

    # ── By risk level ────────────────────────────────────────────────────────────
    lines.append("# HELP honeypot_requests_by_risk Requests grouped by risk level\n# TYPE honeypot_requests_by_risk gauge")
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        lines.append(f'honeypot_requests_by_risk{{level="{level}"}} {by_risk.get(level, 0)}')
    lines.append("")

    # ── By category ─────────────────────────────────────────────────────────────
    lines.append("# HELP honeypot_requests_by_category Requests grouped by attack category\n# TYPE honeypot_requests_by_category gauge")
    for cat, cnt in by_category.items():
        lines.append(f'honeypot_requests_by_category{{category="{cat}"}} {cnt}')
    lines.append("")

    # ── Per-service state ────────────────────────────────────────────────────────
    lines.append("# HELP honeypot_service_enabled Whether each simulated service is enabled (1=yes, 0=no)\n# TYPE honeypot_service_enabled gauge")
    for svc in services:
        lines.append(f'honeypot_service_enabled{{service="{svc["id"]}"}} {1 if svc["enabled"] else 0}')
    lines.append("")

    lines.append("# HELP honeypot_service_tarpitted Whether each simulated service has tarpit enabled (1=yes, 0=no)\n# TYPE honeypot_service_tarpitted gauge")
    for svc in services:
        lines.append(f'honeypot_service_tarpitted{{service="{svc["id"]}"}} {1 if svc["tarpitted"] else 0}')
    lines.append("")

    return PlainTextResponse("\n".join(lines), media_type="text/plain; version=0.0.4; charset=utf-8")
