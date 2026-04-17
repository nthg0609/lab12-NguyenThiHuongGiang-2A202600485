"""Conversation history storage for stateless multi-turn support."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import settings
from app.redis_client import MEMORY_STORE, USE_REDIS, get_redis


class SessionStore:
    def __init__(self, ttl_seconds: int, max_messages: int):
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages

    def _key(self, user_id: str) -> str:
        return f"history:{user_id}"

    def get_history(self, user_id: str) -> list[dict]:
        key = self._key(user_id)
        if USE_REDIS and get_redis() is not None:
            redis_client = get_redis()
            assert redis_client is not None
            data = redis_client.get(key)
            return json.loads(data) if data else []
        return MEMORY_STORE.get(key, [])

    def append_message(self, user_id: str, role: str, content: str) -> list[dict]:
        history = self.get_history(user_id)
        history.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        history = history[-self.max_messages :]
        key = self._key(user_id)
        if USE_REDIS and get_redis() is not None:
            redis_client = get_redis()
            assert redis_client is not None
            redis_client.setex(key, self.ttl_seconds, json.dumps(history))
        else:
            MEMORY_STORE[key] = history
        return history

    def clear_history(self, user_id: str):
        key = self._key(user_id)
        if USE_REDIS and get_redis() is not None:
            redis_client = get_redis()
            assert redis_client is not None
            redis_client.delete(key)
        else:
            MEMORY_STORE.pop(key, None)


session_store = SessionStore(
    ttl_seconds=settings.history_ttl_seconds,
    max_messages=settings.history_max_messages,
)