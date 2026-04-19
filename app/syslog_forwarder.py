"""
SIEM / syslog forwarding — fire-and-forget UDP events in JSON or CEF format.

Configure via:
  SYSLOG_HOST   — IP or hostname of your syslog receiver
  SYSLOG_PORT   — UDP port (default 514)
  SYSLOG_FORMAT — "json" (default) or "cef"
"""

import json
import logging
import socket
from datetime import datetime, timezone

from config import Config

logger = logging.getLogger(__name__)

_SEVERITY = {"CRITICAL": 2, "HIGH": 4, "MEDIUM": 5, "LOW": 6}
_CEF_SEVERITY = {"CRITICAL": 10, "HIGH": 7, "MEDIUM": 5, "LOW": 3}


def _cef(record: dict) -> str:
    risk     = record.get("risk_level", "LOW")
    sev      = _CEF_SEVERITY.get(risk, 3)
    patterns = record.get("flagged_patterns", [])
    if isinstance(patterns, list):
        patterns = ",".join(patterns)
    ext = " ".join([
        f"src={record.get('ip','')}",
        f"request={record.get('path','')}",
        f"requestMethod={record.get('method','')}",
        f"cat={record.get('category','')}",
        f"cs1={record.get('country','')}",
        f"msg={patterns}",
    ])
    return (
        f"CEF:0|AI-Honeypot|HoneypotService|1.0"
        f"|{record.get('category','scan')}"
        f"|AI Honeypot Event"
        f"|{sev}|{ext}"
    )


def _json_msg(record: dict) -> str:
    return json.dumps({
        "timestamp":       record.get("timestamp"),
        "ip":              record.get("ip"),
        "method":          record.get("method"),
        "path":            record.get("path"),
        "category":        record.get("category"),
        "risk_level":      record.get("risk_level"),
        "country":         record.get("country"),
        "city":            record.get("city"),
        "flagged_patterns": record.get("flagged_patterns", []),
    })


def send_syslog_event(record: dict) -> None:
    """Synchronous UDP send — called from asyncio executor in logger.py."""
    if not Config.SYSLOG_HOST:
        return
    try:
        payload = _cef(record) if Config.SYSLOG_FORMAT == "cef" else _json_msg(record)
        risk    = record.get("risk_level", "LOW")
        pri     = 14 * 8 + _SEVERITY.get(risk, 6)   # local6 facility
        ts      = datetime.now(timezone.utc).strftime("%b %d %H:%M:%S")
        msg     = f"<{pri}>{ts} honeypot {payload}"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.sendto(msg.encode("utf-8", errors="replace"),
                        (Config.SYSLOG_HOST, Config.SYSLOG_PORT))
    except Exception as exc:
        logger.debug("Syslog send failed: %s", exc)
