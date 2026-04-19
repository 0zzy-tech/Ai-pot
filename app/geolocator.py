"""
IP geolocation using ip-api.com (free tier, 45 req/min).
Two-layer cache (memory + SQLite) means real API calls are rare.
"""

import ipaddress
import logging
from collections import OrderedDict
from typing import Optional

import httpx

from app.database import get_ip_cache, set_ip_cache
from config import Config

logger = logging.getLogger(__name__)

# ── In-memory LRU cache ───────────────────────────────────────────────────────
_memory_cache: OrderedDict[str, dict] = OrderedDict()

# IPs that should never be looked up
_SKIP_IPS = {"127.0.0.1", "::1", "0.0.0.0", "localhost"}


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def _cache_put(ip: str, geo: dict) -> None:
    if ip in _memory_cache:
        _memory_cache.move_to_end(ip)
    _memory_cache[ip] = geo
    if len(_memory_cache) > Config.GEO_MEMORY_CACHE_SIZE:
        _memory_cache.popitem(last=False)


async def geolocate(ip: str) -> Optional[dict]:
    """
    Returns a dict with keys: country, city, lat, lng, asn
    Returns None for private/loopback IPs or on API failure.
    """
    if ip in _SKIP_IPS or _is_private(ip):
        return None

    # Layer 1: memory cache
    if ip in _memory_cache:
        _memory_cache.move_to_end(ip)
        return _memory_cache[ip]

    # Layer 2: SQLite cache
    cached = await get_ip_cache(ip)
    if cached:
        geo = {
            "country": cached["country"],
            "city":    cached["city"],
            "lat":     cached["lat"],
            "lng":     cached["lng"],
            "asn":     cached["asn"],
            "isp":     cached.get("isp"),
            "hosting": bool(cached["hosting"]) if cached.get("hosting") is not None else None,
        }
        _cache_put(ip, geo)
        return geo

    # Layer 3: live API call
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = Config.GEO_API_URL.format(ip=ip)
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            return None

        geo = {
            "country": data.get("country"),
            "city":    data.get("city"),
            "lat":     data.get("lat"),
            "lng":     data.get("lon"),
            "asn":     data.get("as"),
            "isp":     data.get("isp"),
            "hosting": data.get("hosting"),
        }
        _cache_put(ip, geo)
        await set_ip_cache(ip, geo)
        return geo

    except Exception as exc:
        logger.warning("Geolocation failed for %s: %s", ip, exc)
        return None
