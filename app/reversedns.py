"""
Reverse DNS (PTR record) lookup for attacker IPs.
Uses socket.gethostbyaddr() in a thread executor so it never blocks the event loop.

Results are stored in an in-memory LRU cache so each IP is only looked up once
per process lifetime, independent of the SQLite ip_cache TTL.
"""

import asyncio
import logging
import socket
from collections import OrderedDict

logger = logging.getLogger(__name__)

# In-memory LRU cache: ip → hostname (or None if no PTR record)
_cache: OrderedDict[str, str | None] = OrderedDict()
_CACHE_SIZE = 2000
_SENTINEL = object()  # distinguish "not in cache" from "cached as None"


async def lookup_reverse_dns(ip: str) -> str | None:
    """
    Returns the PTR hostname for the given IP, or None if not found / timeout.
    Each IP is only resolved once; subsequent calls return the cached result.
    """
    # Check in-memory cache first
    if ip in _cache:
        _cache.move_to_end(ip)
        return _cache[ip]

    # Resolve via thread executor (blocking socket call)
    hostname: str | None = None
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyaddr, ip),
            timeout=3.0,
        )
        hostname = result[0]  # (hostname, aliaslist, ipaddrlist)
    except Exception:
        hostname = None

    # Store in LRU cache (even None, to avoid re-resolving)
    _cache[ip] = hostname
    if len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)

    return hostname
