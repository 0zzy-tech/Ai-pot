"""
GreyNoise community API integration.

When GREYNOISE_API_KEY is set, each new public IP is checked against GreyNoise
to distinguish mass internet scanners ("noise") from targeted attackers.

API docs: https://docs.greynoise.io/reference/get_v3-community-ip
Free community tier: 1,000 checks/day.

Response keys used:
  noise          bool   — IP is a known internet scanner (background noise)
  riot           bool   — IP belongs to known benign infrastructure (Google, Cloudflare…)
  classification str    — "malicious" | "benign" | "unknown"
  name           str    — human-readable label (e.g. "Shodan", "Mirai botnet")
"""

import logging

import httpx

from config import Config

logger = logging.getLogger(__name__)

_GREYNOISE_URL = "https://api.greynoise.io/v3/community/{ip}"


async def check_greynoise(ip: str) -> dict | None:
    """
    Returns a dict with keys: greynoise_noise, greynoise_riot,
    greynoise_classification, greynoise_name.
    Returns None if the API key is not set, the IP is unknown to GreyNoise,
    or the call fails.
    """
    if not Config.GREYNOISE_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                _GREYNOISE_URL.format(ip=ip),
                headers={
                    "key":    Config.GREYNOISE_API_KEY,
                    "Accept": "application/json",
                },
            )
            if resp.status_code == 404:
                # IP not found in GreyNoise — return unknown classification
                return {
                    "greynoise_noise":          False,
                    "greynoise_riot":           False,
                    "greynoise_classification": "unknown",
                    "greynoise_name":           None,
                }
            resp.raise_for_status()
            data = resp.json()
            return {
                "greynoise_noise":          bool(data.get("noise", False)),
                "greynoise_riot":           bool(data.get("riot", False)),
                "greynoise_classification": data.get("classification", "unknown"),
                "greynoise_name":           data.get("name") or None,
            }
    except Exception as exc:
        logger.warning("GreyNoise check failed for %s: %s", ip, exc)
        return None
