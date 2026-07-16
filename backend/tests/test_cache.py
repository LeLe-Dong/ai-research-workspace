"""Test caching middleware + TTL cache."""
import pytest
import time
from app.core.cache import TTLCache, dashboard_cache, tags_cache


@pytest.mark.asyncio
async def test_ttl_cache_hit_and_miss():
    """Test that TTL cache returns cached value within TTL."""
    cache = TTLCache(default_ttl=0.5)  # 500ms TTL

    counter = {"value": 0}

    async def factory():
        counter["value"] += 1
        return counter["value"]

    # First call: miss, computes
    v1 = await cache.get_or_set("key", factory)
    assert v1 == 1
    # Second call within TTL: hit
    v2 = await cache.get_or_set("key", factory)
    assert v2 == 1  # not 2
    assert counter["value"] == 1
    # Wait for TTL to expire
    time.sleep(0.6)
    v3 = await cache.get_or_set("key", factory)
    assert v3 == 2  # recomputed
    assert counter["value"] == 2


@pytest.mark.asyncio
async def test_ttl_cache_invalidation():
    """Test manual cache invalidation."""
    cache = TTLCache(default_ttl=10.0)
    counter = {"value": 0}

    async def factory():
        counter["value"] += 1
        return counter["value"]

    v1 = await cache.get_or_set("k", factory)
    assert v1 == 1
    # Invalidate
    cache.invalidate("k")
    v2 = await cache.get_or_set("k", factory)
    assert v2 == 2


@pytest.mark.asyncio
async def test_dashboard_endpoint_cached():
    """Test that /api/v1/dashboard returns within 5s cache."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # First call
        t1 = time.time()
        r1 = await c.get("/api/v1/dashboard")
        d1_ms = (time.time() - t1) * 1000
        # Second call (should hit cache)
        t2 = time.time()
        r2 = await c.get("/api/v1/dashboard")
        d2_ms = (time.time() - t2) * 1000
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Verify Cache-Control header
        assert "max-age=5" in r1.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_tags_endpoint_cached():
    """Test /api/v1/tags returns Cache-Control header."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/tags")
        assert r.status_code == 200
        # Tags are cached 30s
        assert "max-age=30" in r.headers.get("cache-control", "")
