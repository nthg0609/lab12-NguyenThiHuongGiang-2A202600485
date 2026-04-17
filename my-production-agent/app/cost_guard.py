"""Monthly budget protection with Redis-backed accounting."""
from __future__ import annotations

import time

from fastapi import HTTPException

from app.config import settings
from app.redis_client import MEMORY_STORE, USE_REDIS, get_redis

PRICE_PER_1K_INPUT_TOKENS = 0.00015
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006


class CostGuard:
    def __init__(self, monthly_budget_usd: float):
        self.monthly_budget_usd = monthly_budget_usd

    def _month_key(self) -> str:
        return time.strftime("%Y-%m")

    def _usage_key(self, user_id: str) -> str:
        return f"usage:{user_id}:{self._month_key()}"

    def check_budget(self, user_id: str, estimated_cost_usd: float = 0.0) -> None:
        usage = self.get_usage(user_id)
        projected = usage["cost_usd"] + estimated_cost_usd
        if projected > self.monthly_budget_usd:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Monthly budget exceeded",
                    "used_usd": usage["cost_usd"],
                    "budget_usd": self.monthly_budget_usd,
                    "projected_usd": round(projected, 6),
                },
            )

    def record_usage(self, user_id: str, input_tokens: int, output_tokens: int) -> dict:
        cost = round(
            (input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS
            + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS,
            6,
        )
        key = self._usage_key(user_id)

        if USE_REDIS and get_redis() is not None:
            redis_client = get_redis()
            assert redis_client is not None
            pipe = redis_client.pipeline()
            pipe.hincrby(key, "request_count", 1)
            pipe.hincrby(key, "input_tokens", input_tokens)
            pipe.hincrby(key, "output_tokens", output_tokens)
            pipe.hincrbyfloat(key, "cost_usd", cost)
            pipe.expire(key, 40 * 24 * 3600)
            pipe.execute()
        else:
            record = MEMORY_STORE.setdefault(
                key,
                {"request_count": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            )
            record["request_count"] += 1
            record["input_tokens"] += input_tokens
            record["output_tokens"] += output_tokens
            record["cost_usd"] = round(record["cost_usd"] + cost, 6)

        return self.get_usage(user_id)

    def get_usage(self, user_id: str) -> dict:
        key = self._usage_key(user_id)
        if USE_REDIS and get_redis() is not None:
            redis_client = get_redis()
            assert redis_client is not None
            record = redis_client.hgetall(key)
        else:
            record = MEMORY_STORE.get(
                key,
                {"request_count": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            )

        request_count = int(record.get("request_count", 0))
        input_tokens = int(record.get("input_tokens", 0))
        output_tokens = int(record.get("output_tokens", 0))
        cost_usd = round(float(record.get("cost_usd", 0.0)), 6)

        return {
            "user_id": user_id,
            "month": self._month_key(),
            "requests": request_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "budget_usd": self.monthly_budget_usd,
            "budget_remaining_usd": max(0.0, round(self.monthly_budget_usd - cost_usd, 6)),
            "budget_used_pct": round(cost_usd / self.monthly_budget_usd * 100, 2)
            if self.monthly_budget_usd
            else 0.0,
        }


cost_guard = CostGuard(monthly_budget_usd=settings.monthly_budget_usd)