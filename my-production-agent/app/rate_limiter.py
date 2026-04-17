"""Rate limiting with Redis sliding window and dev fallback."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings
from app.redis_client import MEMORY_STORE, USE_REDIS, get_redis


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._fallback_windows: dict[str, deque[float]] = defaultdict(deque)

    def check(self, user_id: str) -> dict:
        if USE_REDIS and get_redis() is not None:
            return self._check_redis(user_id)
        return self._check_memory(user_id)

    def _check_redis(self, user_id: str) -> dict:
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - self.window_seconds * 1000
        key = f"rate:{user_id}"
        redis_client = get_redis()
        assert redis_client is not None

        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start_ms)
        pipe.zcard(key)
        _, current = pipe.execute()

        if current >= self.max_requests:
            oldest = redis_client.zrange(key, 0, 0, withscores=True)
            retry_after = self.window_seconds
            if oldest:
                retry_after = max(
                    1,
                    int((oldest[0][1] + self.window_seconds * 1000 - now_ms) / 1000) + 1,
                )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.max_requests} req/{self.window_seconds}s",
                headers={"Retry-After": str(retry_after)},
            )

        pipe = redis_client.pipeline()
        pipe.zadd(key, {str(now_ms): now_ms})
        pipe.expire(key, self.window_seconds + 5)
        pipe.execute()
        return {
            "limit": self.max_requests,
            "remaining": self.max_requests - current - 1,
        }

    def _check_memory(self, user_id: str) -> dict:
        now = time.time()
        window = self._fallback_windows[user_id]
        while window and window[0] < now - self.window_seconds:
            window.popleft()
        if len(window) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.max_requests} req/{self.window_seconds}s",
                headers={"Retry-After": str(self.window_seconds)},
            )
        window.append(now)
        MEMORY_STORE[f"rate:{user_id}"] = list(window)
        return {
            "limit": self.max_requests,
            "remaining": self.max_requests - len(window),
        }


rate_limiter = RateLimiter(
    max_requests=settings.rate_limit_per_minute,
    window_seconds=settings.rate_limit_window_seconds,
)