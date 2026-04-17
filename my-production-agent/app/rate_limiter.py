from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time

class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 5, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        current_time = time.time()

        if client_ip not in self.clients:
            self.clients[client_ip] = []

        request_times = self.clients[client_ip]
        request_times = [t for t in request_times if current_time - t < self.window_seconds]
        request_times.append(current_time)
        self.clients[client_ip] = request_times

        if len(request_times) > self.max_requests:
            raise HTTPException(status_code=429, detail="Too many requests")

        response = await call_next(request)
        return response