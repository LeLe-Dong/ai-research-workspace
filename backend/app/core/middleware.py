"""Caching middleware: add Cache-Control headers for GET requests on cacheable endpoints."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time


CACHE_RULES = {
    "/api/v1/dashboard": 5,           # Dashboard: 5s
    "/api/v1/tags": 30,               # Tags: 30s
    "/api/v1/completed-researches": 10,  # KB list: 10s
    "/api/v1/researches": 5,          # Research list: 5s
    "/api/v1/admin/agent-mode": 5,    # Agent mode: 5s
    "/api/v1/admin/restart-status": 5,
    "/api/v1/admin/stuck-researches": 5,
    "/v1/models": 60,                 # Model list: 1 min
    "/health": 0,                     # No cache
}


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control: max-age=N for matching GET requests."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method == "GET":
            path = request.url.path
            for prefix, ttl in CACHE_RULES.items():
                if path.startswith(prefix) and ttl > 0:
                    response.headers["Cache-Control"] = f"public, max-age={ttl}"
                    break
        return response
