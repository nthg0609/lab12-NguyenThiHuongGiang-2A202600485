"""Production AI agent combining auth, rate limiting, budgets, and stateless history."""
from __future__ import annotations

import json
import logging
import signal
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import cost_guard
from app.rate_limiter import rate_limiter
from app.redis_client import USE_REDIS, is_redis_connected, storage_name
from app.session_store import session_store
from utils.mock_llm import ask as llm_ask

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
IS_READY = False
REQUEST_COUNT = 0
ERROR_COUNT = 0


class AskRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    user_id: str
    question: str
    answer: str
    model: str
    timestamp: str
    history_messages: int
    storage: str
    requests_remaining: int
    budget_remaining_usd: float


def answer_with_history(question: str, history: list[dict]) -> str:
    question_lower = question.lower()
    previous_user_messages = [m["content"] for m in history if m.get("role") == "user"]

    if any(
        phrase in question_lower
        for phrase in [
            "what did i just say",
            "what was my previous question",
            "what did i ask before",
            "toi vua hoi gi",
        ]
    ):
        if previous_user_messages:
            return f"Your previous question was: {previous_user_messages[-1]}"
        return "I do not have any previous question stored for this user yet."

    return llm_ask(question)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global IS_READY
    logger.info(
        json.dumps(
            {
                "event": "startup",
                "app": settings.app_name,
                "version": settings.app_version,
                "environment": settings.environment,
                "storage": storage_name(),
                "redis_connected": is_redis_connected(),
            }
        )
    )
    time.sleep(0.1)
    IS_READY = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    IS_READY = False
    logger.info(json.dumps({"event": "shutdown"}))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global REQUEST_COUNT, ERROR_COUNT
    start = time.time()
    REQUEST_COUNT += 1
    try:
        response: Response = await call_next(request)
    except Exception:
        ERROR_COUNT += 1
        raise

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if "server" in response.headers:
        del response.headers["server"]

    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info(
        json.dumps(
            {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": duration_ms,
            }
        )
    )
    return response


@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "storage": storage_name(),
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key, body: user_id + question)",
            "history": "GET /history/{user_id} (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(body: AskRequest, request: Request, _key: str = Depends(verify_api_key)):
    if not IS_READY:
        raise HTTPException(503, "Service not ready")

    rate_info = rate_limiter.check(body.user_id)
    history_before = session_store.get_history(body.user_id)

    input_tokens = len(body.question.split()) * 2
    estimated_output_tokens = max(20, input_tokens)
    estimated_cost = (input_tokens / 1000) * 0.00015 + (estimated_output_tokens / 1000) * 0.0006
    cost_guard.check_budget(body.user_id, estimated_cost_usd=estimated_cost)

    logger.info(
        json.dumps(
            {
                "event": "agent_call",
                "user_id": body.user_id,
                "history_messages": len(history_before),
                "client": str(request.client.host) if request.client else "unknown",
            }
        )
    )

    answer = answer_with_history(body.question, history_before)
    session_store.append_message(body.user_id, "user", body.question)
    history_after = session_store.append_message(body.user_id, "assistant", answer)

    output_tokens = len(answer.split()) * 2
    usage = cost_guard.record_usage(body.user_id, input_tokens=input_tokens, output_tokens=output_tokens)

    return AskResponse(
        user_id=body.user_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
        history_messages=len(history_after),
        storage=storage_name(),
        requests_remaining=rate_info["remaining"],
        budget_remaining_usd=usage["budget_remaining_usd"],
    )


@app.get("/history/{user_id}", tags=["Agent"])
def get_history(user_id: str, _key: str = Depends(verify_api_key)):
    history = session_store.get_history(user_id)
    return {
        "user_id": user_id,
        "messages": history,
        "count": len(history),
        "storage": storage_name(),
    }


@app.delete("/history/{user_id}", tags=["Agent"])
def clear_history(user_id: str, _key: str = Depends(verify_api_key)):
    session_store.clear_history(user_id)
    return {"cleared": user_id}


@app.get("/health", tags=["Operations"])
def health():
    redis_ok = is_redis_connected() if USE_REDIS else "N/A"
    status = "ok" if (not USE_REDIS or redis_ok) else "degraded"
    checks = {
        "llm": "mock" if not settings.openai_api_key else "configured",
        "storage": storage_name(),
        "redis_connected": redis_ok,
    }
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": REQUEST_COUNT,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not IS_READY:
        raise HTTPException(503, "Not ready")
    if settings.redis_url and not settings.allow_in_memory_fallback and not is_redis_connected():
        raise HTTPException(503, "Redis not available")
    return {
        "ready": True,
        "storage": storage_name(),
        "redis_connected": is_redis_connected() if USE_REDIS else False,
    }


@app.get("/metrics", tags=["Operations"])
def metrics(user_id: str, _key: str = Depends(verify_api_key)):
    usage = cost_guard.get_usage(user_id)
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": REQUEST_COUNT,
        "error_count": ERROR_COUNT,
        "storage": storage_name(),
        "usage": usage,
    }


def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info("Starting %s on %s:%s", settings.app_name, settings.host, settings.port)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )