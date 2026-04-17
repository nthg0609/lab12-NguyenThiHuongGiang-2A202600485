from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class CostGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_cost: int = 100):
        super().__init__(app)
        self.max_cost = max_cost
        self.current_cost = 0

    async def dispatch(self, request: Request, call_next):
        if self.current_cost >= self.max_cost:
            raise HTTPException(status_code=402, detail="Cost limit exceeded")

        response = await call_next(request)
        self.current_cost += 1  # Increment cost for each request
        return response