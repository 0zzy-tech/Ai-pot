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

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import Request

from app.broadcaster import manager
from app.classifier import classify_request
from app.database import (
    count_critical_requests_from_ip,
    count_recent_requests,
    insert_request,
)
from app.geolocator import geolocate
from app.threatfeeds import is_known_c2
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

        # Reverse DNS (own in-memory LRU cache — one lookup per IP per process)
        rdns = None
        if geo is not None and ip not in {"unknown", "127.0.0.1", "::1"}:
            from app.reversedns import lookup_reverse_dns
            rdns = await lookup_reverse_dns(ip)

        # AbuseIPDB reputation check (cached in ip_cache alongside geo data)
        rep = None
        if Config.ABUSEIPDB_API_KEY and ip not in {"unknown", "127.0.0.1", "::1"}:
            from app.abuseipdb import check_reputation
            from app.database import get_ip_cache, set_ip_cache
            cached = await get_ip_cache(ip)
            if cached and cached.get("abuse_score") is not None:
                rep = {
                    "abuse_score":   cached["abuse_score"],
                    "abuse_reports": cached["abuse_reports"],
                    "is_tor":        bool(cached.get("is_tor")),
                    "isp":           cached.get("isp"),
                }
            else:
                rep = await check_reputation(ip)
                if rep and geo:
                    # Merge reputation into geo dict so set_ip_cache persists both
                    merged = {**geo, **rep, "reverse_dns": rdns}
                    await set_ip_cache(ip, merged)
        elif geo:
            # No AbuseIPDB key — still persist geo + reverse DNS
            from app.database import set_ip_cache
            await set_ip_cache(ip, {**geo, "reverse_dns": rdns})

        # GreyNoise classification (cached in ip_cache)
        gn = None
        if Config.GREYNOISE_API_KEY and ip not in {"unknown", "127.0.0.1", "::1"}:
            from app.greynoise import check_greynoise
            from app.database import get_ip_cache, set_ip_cache
            gn_cached = await get_ip_cache(ip)
            if gn_cached and gn_cached.get("greynoise_classification") is not None:
                gn = {
                    "greynoise_noise":          bool(gn_cached.get("greynoise_noise")),
                    "greynoise_riot":           bool(gn_cached.get("greynoise_riot")),
                    "greynoise_classification": gn_cached.get("greynoise_classification"),
                    "greynoise_name":           gn_cached.get("greynoise_name"),
                }
            else:
                gn = await check_greynoise(ip)
                if gn:
                    merged = {**(geo or {}), **(rep or {}), "reverse_dns": rdns, **gn}
                    from app.database import set_ip_cache
                    await set_ip_cache(ip, merged)

        # Threat feed checks (sync in-memory lookups — before insert so is_c2 is persisted)
        c2_hit = is_known_c2(ip)
        from app.threatfox import get_threatfox_hit
        threatfox_hit = get_threatfox_hit(ip)

        # ML scoring (cold-start safe — returns empty dict until models are trained)
        from app.ml_engine import engine as _ml
        ml_request_scores = _ml.score_request({
            "body_len":      len(body_text),
            "path":          path,
            "method":        method,
            "headers":       headers,
            "flagged_count": len(flagged),
            "recent_60s":    recent_60s,
            "recent_600s":   recent_600s,
            "is_c2":         c2_hit,
            "is_tor":        bool(rep.get("is_tor")) if rep else False,
            "abuse_score":   rep.get("abuse_score", 0) if rep else 0,
            "is_hosting":    bool(geo.get("hosting")) if geo else False,
            "category":      category,
        })
        ml_session_scores = await _ml.score_session_async(ip)

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
            "is_c2":            1 if c2_hit else 0,
        }

        row_id = await insert_request(record)

        # Auto-block IPs that repeatedly trigger CRITICAL alerts
        if (Config.AUTO_BLOCK_ENABLED
                and risk_level == "CRITICAL"
                and ip not in {"unknown", "127.0.0.1", "::1"}):
            from app import service_registry
            if not service_registry.is_ip_blocked(ip):
                crit_count = await count_critical_requests_from_ip(ip, Config.AUTO_BLOCK_WINDOW)
                if crit_count >= Config.AUTO_BLOCK_THRESHOLD:
                    reason = (
                        f"auto: {crit_count} CRITICAL requests in "
                        f"{Config.AUTO_BLOCK_WINDOW}s"
                    )
                    await service_registry.block_ip(ip, reason)
                    await manager.broadcast({"type": "ip_blocked", "data": {"ip": ip, "reason": reason}})

        # Fire webhooks for high-severity events (non-blocking)
        if Config.WEBHOOK_URLS and record["risk_level"] in Config.WEBHOOK_RISK_LEVELS:
            from app.webhooks import fire_webhooks
            asyncio.create_task(fire_webhooks(record))

        # Email alerts (non-blocking, runs in executor)
        if Config.SMTP_HOST and Config.SMTP_TO and record["risk_level"] in Config.EMAIL_RISK_LEVELS:
            from app.emailer import send_alert_email
            asyncio.create_task(send_alert_email(record))

        # SIEM / syslog forwarding (fire-and-forget UDP, non-blocking)
        if Config.SYSLOG_HOST:
            from app.syslog_forwarder import send_syslog_event
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, send_syslog_event, record)

        # Deception callback — log to dedicated table when attacker follows deception URL
        if path.startswith("/track/"):
            from app.database import log_deception_callback
            token = path.split("/track/", 1)[-1].split("?")[0]
            asyncio.create_task(log_deception_callback(token, ip))

        # Include operator note if set for this IP
        from app import service_registry as _sr
        ip_note = _sr.get_ip_note(ip)

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
            "abuse_score":      rep["abuse_score"] if rep else None,
            "is_tor":           rep["is_tor"]      if rep else False,
            "note":             ip_note,
            "is_c2":            c2_hit,
            "isp":              geo.get("isp")     if geo else None,
            "hosting":          geo.get("hosting") if geo else None,
            "reverse_dns":      rdns,
            "threatfox_hit":    threatfox_hit,
            "greynoise_classification": gn["greynoise_classification"] if gn else None,
            "greynoise_noise":          gn["greynoise_noise"]          if gn else None,
            "greynoise_riot":           gn["greynoise_riot"]           if gn else None,
            "greynoise_name":           gn["greynoise_name"]           if gn else None,
            "ml_anomaly_score":         ml_request_scores.get("anomaly_score"),
            "ml_risk_score":            ml_request_scores.get("risk_score"),
            "ml_bot_probability":       ml_session_scores.get("bot_probability"),
            "ml_cluster_id":            ml_session_scores.get("cluster_id"),
        }
        await manager.broadcast({"type": "new_request", "data": broadcast_data})

    except Exception as exc:
        logger.error("log_request failed: %s", exc, exc_info=True)
