"""
Central request logging pipeline.
Called as asyncio.create_task() so it never delays the fake response.

Pipeline:
  1. Extract real client IP (handles proxies)
  2. Classify request (sync, fast)
  3. Geolocate IP (async, cached)
  4. Write to SQLite
  5. Broadcast to WebSocket clients
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import Request

from app.broadcaster import manager
from app.classifier import classify_request
from app.database import count_recent_requests, insert_request
from app.geolocator import geolocate
from config import Config

logger = logging.getLogger(__name__)


def _real_ip(request: Request) -> str:
    """Extract the actual client IP, respecting common proxy headers."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else "unknown"


async def log_request(
    request: Request,
    body: bytes,
    status_code: int,
) -> None:
    try:
        ip = _real_ip(request)
        path = request.url.path
        method = request.method
        headers = dict(request.headers)

        # Cap body size
        body_text = body[: Config.MAX_BODY_SIZE_BYTES].decode("utf-8", errors="replace")

        try:
            body_json: dict = json.loads(body_text) if body_text.strip() else {}
        except (json.JSONDecodeError, ValueError):
            body_json = {}

        # Recent request counts for rate-based classification
        recent_60s, recent_600s = 0, 0
        try:
            recent_60s  = await count_recent_requests(ip, 60)
            recent_600s = await count_recent_requests(ip, 600)
        except Exception:
            pass

        # Classify
        category, risk_level, flagged = classify_request(
            method=method,
            path=path,
            headers=headers,
            body_text=body_text,
            body_json=body_json,
            recent_count_60s=recent_60s,
            recent_count_600s=recent_600s,
        )

        # Geolocate (cached)
        geo = await geolocate(ip)

        record = {
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "ip":               ip,
            "method":           method,
            "path":             path,
            "headers":          json.dumps(headers),
            "body":             body_text or None,
            "category":         category,
            "risk_level":       risk_level,
            "user_agent":       headers.get("user-agent", ""),
            "country":          geo["country"] if geo else None,
            "city":             geo["city"]    if geo else None,
            "lat":              geo["lat"]     if geo else None,
            "lng":              geo["lng"]     if geo else None,
            "asn":              geo["asn"]     if geo else None,
            "flagged_patterns": json.dumps(flagged),
        }

        row_id = await insert_request(record)

        # Build broadcast payload (no full headers/body — keep WS messages small)
        broadcast_data = {
            "id":               row_id,
            "timestamp":        record["timestamp"],
            "ip":               ip,
            "method":           method,
            "path":             path,
            "category":         category,
            "risk_level":       risk_level,
            "user_agent":       record["user_agent"],
            "country":          record["country"],
            "city":             record["city"],
            "lat":              record["lat"],
            "lng":              record["lng"],
            "asn":              record["asn"],
            "flagged_patterns": flagged,
        }
        await manager.broadcast({"type": "new_request", "data": broadcast_data})

    except Exception as exc:
        logger.error("log_request failed: %s", exc, exc_info=True)
