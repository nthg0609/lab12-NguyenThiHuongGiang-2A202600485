"""Shared Redis connection with optional development fallback."""
from __future__ import annotations

import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis = None
USE_REDIS = False
MEMORY_STORE: dict[str, object] = {}

try:
    if settings.redis_url:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
        _redis.ping()
        USE_REDIS = True
        logger.info("Connected to Redis")
    elif not settings.allow_in_memory_fallback:
        raise RuntimeError("REDIS_URL must be set when in-memory fallback is disabled.")
except Exception as exc:  # pragma: no cover - startup fallback path
    if not settings.allow_in_memory_fallback:
        raise
    USE_REDIS = False
    _redis = None
    logger.warning("Redis unavailable, using in-memory fallback: %s", exc)


def get_redis():
    return _redis


def is_redis_connected() -> bool:
    if not USE_REDIS or _redis is None:
        return False
    try:
        _redis.ping()
        return True
    except Exception:
        return False


def storage_name() -> str:
    return "redis" if USE_REDIS else "in-memory"