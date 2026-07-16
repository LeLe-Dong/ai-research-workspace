"""Test /api/v1/expand/goal endpoint."""
import pytest


@pytest.mark.asyncio
async def test_expand_requires_goal(client):
    """Empty goal returns 422 (Pydantic validation)."""
    r = await client.post("/api/v1/expand/goal", json={})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_expand_too_short_goal(client):
    """Goal under 2 chars returns 422."""
    r = await client.post("/api/v1/expand/goal", json={"goal": "a"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_expand_without_key_returns_503(client):
    """Without AIRW_STEPFUN_API_KEY, returns 503 (service unavailable)."""
    # Key is now in .env, so this test simulates missing key by overriding settings
    from app.core.config import settings
    original = settings.stepfun_api_key
    settings.stepfun_api_key = ""
    try:
        r = await client.post("/api/v1/expand/goal", json={"goal": "对比 PostgreSQL 和 MySQL"})
        assert r.status_code == 503
        body = r.json()
        assert "AIRW_STEPFUN_API_KEY" in body.get("detail", "") or "未启用" in body.get("detail", "")
    finally:
        settings.stepfun_api_key = original


@pytest.mark.asyncio
async def test_expand_with_invalid_key_returns_502(client):
    """With invalid key, stepfun returns 401 → we wrap to 502."""
    from app.core.config import settings
    original = settings.stepfun_api_key
    settings.stepfun_api_key = "invalid_test_key_xxxxxxxxxxxxxx"
    try:
        r = await client.post("/api/v1/expand/goal", json={"goal": "对比 PostgreSQL 和 MySQL"})
        # 502 because stepfun returned 401 (auth error)
        assert r.status_code == 502
        body = r.json()
        assert "401" in body.get("detail", "") or "LLM" in body.get("detail", "")
    finally:
        settings.stepfun_api_key = original
