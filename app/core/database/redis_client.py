from __future__ import annotations

import json
import logging
from typing import Any, List

from redis.asyncio import Redis

from ..config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


async def get_redis() -> Redis | None:
    global _redis

    if not settings.REDIS_ENABLED:
        return None

    if _redis is not None:
        return _redis

    try:
        _redis = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        await _redis.ping()
        logger.info("Redis connected")
        return _redis
    except Exception:
        logger.exception("Failed to connect Redis. Continuing without Redis-backed queue/presence.")
        _redis = None
        return None


async def close_redis() -> None:
    global _redis
    if _redis is None:
        return

    try:
        await _redis.aclose()
    except Exception:
        logger.exception("Failed while closing Redis connection")
    finally:
        _redis = None


async def enqueue_pending(user_id: str, payload: dict[str, Any]) -> None:
    client = await get_redis()
    if client is None:
        return

    key = f"pending:{user_id}"
    await client.rpush(key, json.dumps(payload, ensure_ascii=False))


async def pop_all_pending(user_id: str) -> List[dict[str, Any]]:
    client = await get_redis()
    if client is None:
        return []

    key = f"pending:{user_id}"
    raw_items = await client.lrange(key, 0, -1)
    if raw_items:
        await client.delete(key)

    out: list[dict[str, Any]] = []
    for raw in raw_items:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                out.append(decoded)
        except Exception:
            continue

    return out


async def set_presence_online(user_id: str) -> None:
    client = await get_redis()
    if client is None:
        return

    await client.hset("presence:users", user_id, "online")


async def set_presence_offline(user_id: str) -> None:
    client = await get_redis()
    if client is None:
        return

    await client.hset("presence:users", user_id, "offline")


async def get_presence(user_id: str) -> str | None:
    client = await get_redis()
    if client is None:
        return None

    return await client.hget("presence:users", user_id)


async def cache_location(booking_id: str, user_id: str, payload: dict[str, Any]) -> None:
    client = await get_redis()
    if client is None:
        return

    key = f"location:{booking_id}:{user_id}"
    await client.set(key, json.dumps(payload, ensure_ascii=False), ex=60)


async def get_cached_location(booking_id: str, user_id: str) -> dict[str, Any] | None:
    client = await get_redis()
    if client is None:
        return None

    raw = await client.get(f"location:{booking_id}:{user_id}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def is_duplicate_message(sender_id: str, client_message_id: str) -> bool:
    """Atomically check-and-set a dedup key. Returns True if the message is a duplicate."""
    client = await get_redis()
    if client is None:
        return False

    key = f"msg_dedup:{sender_id}:{client_message_id}"
    result = await client.set(key, "1", ex=86400, nx=True)
    return result is None
