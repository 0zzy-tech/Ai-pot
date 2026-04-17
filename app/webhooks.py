"""
Webhook alerting module.

Fires HTTP POST notifications when a high-severity request is logged.
Configured entirely via environment variables — no UI config needed.

Supported formats:
  - "json"    — plain JSON with key request fields (default)
  - "slack"   — Slack Incoming Webhook format (attachments with color)
  - "discord" — Discord webhook format (embeds)

Set WEBHOOK_URLS to a comma-separated list of URLs to POST to.
Set WEBHOOK_RISK_LEVELS to control which risk levels trigger alerts (default: CRITICAL,HIGH).
"""

import logging

import httpx

from config import Config

logger = logging.getLogger(__name__)

_RISK_COLORS = {
    "CRITICAL": {"slack": "#f85149", "discord": 0xF85149},
    "HIGH":     {"slack": "#d29922", "discord": 0xD29922},
    "MEDIUM":   {"slack": "#e3b341", "discord": 0xE3B341},
    "LOW":      {"slack": "#3fb950", "discord": 0x3FB950},
}


def _build_payload(record: dict) -> dict:
    risk  = record.get("risk_level", "UNKNOWN")
    ip    = record.get("ip", "?")
    path  = record.get("path", "?")
    cat   = record.get("category", "?")
    flags = record.get("flagged_patterns", "[]")
    ts    = record.get("timestamp", "")
    country = record.get("country") or "?"

    fmt = Config.WEBHOOK_FORMAT

    if fmt == "slack":
        color = _RISK_COLORS.get(risk, {}).get("slack", "#8b949e")
        return {
            "text": f":warning: AI Honeypot Alert — *{risk}* event detected",
            "attachments": [{
                "color": color,
                "fields": [
                    {"title": "Risk",     "value": risk,    "short": True},
                    {"title": "IP",       "value": ip,      "short": True},
                    {"title": "Country",  "value": country, "short": True},
                    {"title": "Category", "value": cat,     "short": True},
                    {"title": "Path",     "value": path,    "short": False},
                    {"title": "Patterns", "value": flags,   "short": False},
                    {"title": "Time",     "value": ts,      "short": False},
                ],
            }],
        }

    if fmt == "discord":
        color = _RISK_COLORS.get(risk, {}).get("discord", 0x8B949E)
        return {
            "embeds": [{
                "title": f"AI Honeypot — {risk} Event",
                "color": color,
                "fields": [
                    {"name": "IP",       "value": ip,      "inline": True},
                    {"name": "Country",  "value": country, "inline": True},
                    {"name": "Category", "value": cat,     "inline": True},
                    {"name": "Path",     "value": path,    "inline": False},
                    {"name": "Patterns", "value": flags,   "inline": False},
                    {"name": "Time",     "value": ts,      "inline": False},
                ],
            }],
        }

    # Generic JSON
    return {
        "event":     "honeypot_alert",
        "risk_level": risk,
        "ip":        ip,
        "country":   country,
        "category":  cat,
        "path":      path,
        "flagged_patterns": flags,
        "timestamp": ts,
    }


async def fire_webhooks(record: dict) -> None:
    """Post alert to all configured webhook URLs. Errors are logged, never raised."""
    if not Config.WEBHOOK_URLS:
        return

    payload = _build_payload(record)
    timeout = httpx.Timeout(Config.WEBHOOK_TIMEOUT_SECS)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in Config.WEBHOOK_URLS:
            try:
                resp = await client.post(url, json=payload)
                logger.info("Webhook %s → HTTP %d", url[:40], resp.status_code)
            except Exception as exc:
                logger.warning("Webhook %s failed: %s", url[:40], exc)
