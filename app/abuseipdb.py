"""
AbuseIPDB reputation lookup.

When ABUSEIPDB_API_KEY is set, each new IP is checked against the AbuseIPDB
database after geolocation. Results are cached in ip_cache alongside geo data
so subsequent requests from the same IP don't incur an extra API call.

API docs: https://docs.abuseipdb.com/#check-endpoint
Free tier: 1,000 checks/day.
"""

import logging

import httpx

from config import Config

logger = logging.getLogger(__name__)

_ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2/check"


async def check_reputation(ip: str) -> dict | None:
    """
    Returns a dict with keys: abuse_score, abuse_reports, is_tor, isp
    Returns None if the API key is not set, the IP is private, or the call fails.
    """
    if not Config.ABUSEIPDB_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                _ABUSEIPDB_URL,
                params={
                    "ipAddress":    ip,
                    "maxAgeInDays": Config.ABUSEIPDB_MAX_AGE_DAYS,
                },
                headers={
                    "Key":    Config.ABUSEIPDB_API_KEY,
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "abuse_score":   data.get("abuseConfidenceScore", 0),
                "abuse_reports": data.get("totalReports", 0),
                "is_tor":        bool(data.get("isTor", False)),
                "isp":           data.get("isp", ""),
            }
    except Exception as exc:
        logger.warning("AbuseIPDB check failed for %s: %s", ip, exc)
        return None
