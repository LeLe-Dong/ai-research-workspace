"""Simple in-memory cache for hot endpoints."""
import time
from typing import Any, Callable
import asyncio
import functools


class TTLCache:
    """Simple thread-safe-ish TTL cache (single-process)."""

    def __init__(self, default_ttl: float = 5.0):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Get a value from cache. Returns None if missing or expired."""
        now = time.time()
        if key not in self._cache:
            return None
        ts, val = self._cache[key]
        if now - ts >= self._default_ttl:
            del self._cache[key]
            return None
        return val

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Set a value in cache with optional custom TTL."""
        self._cache[key] = (time.time(), value)

    async def get_or_set(self, key: str, factory: Callable[[], Any], ttl: float | None = None) -> Any:
        existing = await self.get(key)
        if existing is not None:
            return existing
        # Compute
        if asyncio.iscoroutinefunction(factory):
            val = await factory()
        else:
            val = factory()
        await self.set(key, val, ttl)
        return val

    def invalidate(self, key: str | None = None):
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)


# Singleton cache instances
dashboard_cache = TTLCache(default_ttl=5.0)  # 5s - dashboard data
tags_cache = TTLCache(default_ttl=30.0)  # 30s - tags change rarely
agent_mode_cache = TTLCache(default_ttl=10.0)  # 10s - mode rarely changes
