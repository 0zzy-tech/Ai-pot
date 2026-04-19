"""
Threat intelligence feed integration.
Downloads the Feodo Tracker C2 botnet IP blocklist and refreshes it every 24 hours.
Provides a sync lookup used in the logging pipeline.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_c2_ips: set[str] = set()
_last_refresh: datetime | None = None

# Feodo Tracker recommended blocklist (public, no API key needed)
FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist_recommended.txt"
REFRESH_INTERVAL_SECS = 86_400   # 24 hours


def is_known_c2(ip: str) -> bool:
    """Sync lookup — safe to call from the logging pipeline."""
    return ip in _c2_ips


def feed_stats() -> dict:
    return {
        "c2_count":     len(_c2_ips),
        "last_refresh": _last_refresh.isoformat() if _last_refresh else None,
    }


async def refresh_feeds() -> None:
    global _c2_ips, _last_refresh
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(FEODO_URL, follow_redirects=True)
            resp.raise_for_status()
        new_set: set[str] = set()
        for line in resp.text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                new_set.add(line)
        _c2_ips = new_set
        _last_refresh = datetime.now(timezone.utc)
        logger.info("Feodo Tracker refreshed — %d C2 IPs", len(_c2_ips))
    except Exception as exc:
        logger.warning("Threat feed refresh failed: %s", exc)


async def threat_feed_task() -> None:
    """Background loop — refreshes feeds every 24 hours.
    The initial download is handled at startup before this task is created."""
    while True:
        await asyncio.sleep(REFRESH_INTERVAL_SECS)
        await refresh_feeds()
