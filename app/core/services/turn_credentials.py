from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import settings

logger = logging.getLogger(__name__)

# In-process cache for TURN credentials. Metered API calls add 5-10 seconds
# to every call initiation when un-cached; refreshing every 30 minutes is
# more than safe for static-credential providers like Metered.
_CACHE_TTL_SECONDS = 30 * 60
_FETCH_TIMEOUT_SECONDS = 2  # was 8 — keep call initiation snappy
_cache: dict[str, tuple[float, list[dict[str, Any]], str]] = {}
_cache_lock = asyncio.Lock()

# Hardcoded Metered TURN credentials — used when the dynamic API call fails.
# TURN is required for symmetric NAT (most mobile carriers); STUN-only will not work.
_METERED_TURN_ICE_SERVERS: list[dict[str, Any]] = [
    {"urls": "stun:stun.relay.metered.ca:80"},
    {
        "urls": "turn:global.relay.metered.ca:80",
        "username": "55ebcd964c2936d0dc1db8d2",
        "credential": "WIir6zhTPXOiW156",
    },
    {
        "urls": "turn:global.relay.metered.ca:80?transport=tcp",
        "username": "55ebcd964c2936d0dc1db8d2",
        "credential": "WIir6zhTPXOiW156",
    },
    {
        "urls": "turn:global.relay.metered.ca:443",
        "username": "55ebcd964c2936d0dc1db8d2",
        "credential": "WIir6zhTPXOiW156",
    },
    {
        "urls": "turns:global.relay.metered.ca:443?transport=tcp",
        "username": "55ebcd964c2936d0dc1db8d2",
        "credential": "WIir6zhTPXOiW156",
    },
]


def _default_ice_servers() -> list[dict[str, Any]]:
    fallback = settings.TURN_FALLBACK_ICE_SERVERS
    if isinstance(fallback, list) and fallback:
        return fallback
    return _METERED_TURN_ICE_SERVERS


def _fetch_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


async def _fetch_from_metered(region: str) -> Optional[tuple[list[dict[str, Any]], str]]:
    """Direct fetch from Metered, no cache. Returns None on failure."""
    api_key = (settings.METERED_API_KEY or "").strip()
    domain = (settings.METERED_TURN_DOMAIN or "").strip()

    if not api_key or not domain:
        return None

    params = {"apiKey": api_key}
    if region:
        params["region"] = region

    url = f"https://{domain}/api/v1/turn/credentials?{urlencode(params)}"

    try:
        data = await asyncio.to_thread(_fetch_json, url)
    except Exception:
        logger.warning("TURN credential fetch from Metered failed; using fallback ICE servers")
        return None

    if not isinstance(data, list) or not data:
        return None

    normalized = [item for item in data if isinstance(item, dict) and item.get("urls")]
    if not normalized:
        return None

    return normalized, "metered"


async def fetch_turn_credentials(region: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """
    Returns tuple(ice_servers, source).
    source is one of: metered, fallback

    Uses an in-process cache (30 min TTL) so call initiation never blocks on
    the Metered API. On cache miss, fetches with a short timeout; if that
    fails, returns the static fallback immediately.
    """
    chosen_region = (region or settings.TURN_REGION or "global").strip() or "global"
    now = time.monotonic()

    cached = _cache.get(chosen_region)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1], cached[2]

    # Coordinate concurrent misses so only one request hits Metered at a time.
    async with _cache_lock:
        cached = _cache.get(chosen_region)
        if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1], cached[2]

        result = await _fetch_from_metered(chosen_region)
        if result is None:
            servers, source = _default_ice_servers(), "fallback"
        else:
            servers, source = result

        _cache[chosen_region] = (time.monotonic(), servers, source)
        return servers, source
