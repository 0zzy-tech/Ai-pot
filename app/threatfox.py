"""
ThreatFox IOC feed integration (https://threatfox.abuse.ch).
Downloads the recent IP:port IOC list and refreshes it every 24 hours.
No API key required.

Provides a sync lookup used in the logging pipeline.
"""

import asyncio
import csv
import io
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_threatfox_ips: dict[str, str] = {}   # ip → malware family name
_last_refresh: datetime | None = None

THREATFOX_URL = "https://threatfox.abuse.ch/export/csv/ip-port/recent/"
REFRESH_INTERVAL_SECS = 86_400  # 24 hours


def get_threatfox_hit(ip: str) -> str | None:
    """Sync lookup — safe to call from the logging pipeline.
    Returns malware family name if the IP is a known ThreatFox IOC, else None."""
    return _threatfox_ips.get(ip)


def threatfox_stats() -> dict:
    return {
        "ioc_count":    len(_threatfox_ips),
        "last_refresh": _last_refresh.isoformat() if _last_refresh else None,
    }


async def refresh_threatfox() -> None:
    global _threatfox_ips, _last_refresh
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(THREATFOX_URL, follow_redirects=True)
            resp.raise_for_status()

        new_map: dict[str, str] = {}
        reader = csv.reader(io.StringIO(resp.text))
        for row in reader:
            # Skip comment lines and the header
            if not row or row[0].startswith("#"):
                continue
            # CSV columns (0-indexed):
            # 0: first_seen_utc  1: ioc_id  2: ioc_value (ip:port)
            # 3: ioc_type        4: threat_type  5: fk_malware
            # 6: malware_alias   7: malware_printable  ...
            if len(row) < 8:
                continue
            ioc_value = row[2].strip().strip('"')
            malware   = row[7].strip().strip('"') or row[5].strip().strip('"')
            if ":" in ioc_value:
                ip = ioc_value.rsplit(":", 1)[0]
                if ip:
                    new_map[ip] = malware or "Unknown"

        _threatfox_ips = new_map
        _last_refresh = datetime.now(timezone.utc)
        logger.info("ThreatFox refreshed — %d IP IOCs", len(_threatfox_ips))
    except Exception as exc:
        logger.warning("ThreatFox feed refresh failed: %s", exc)


async def threatfox_task() -> None:
    """Background loop — refreshes the ThreatFox feed every 24 hours.
    The initial download is handled at startup before this task is created."""
    while True:
        await asyncio.sleep(REFRESH_INTERVAL_SECS)
        await refresh_threatfox()
