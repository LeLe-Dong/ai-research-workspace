"""Test API endpoints (CRUD + history)."""
import pytest
import json


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "agent_mode" in data


@pytest.mark.asyncio
async def test_create_research(client):
    payload = {
        "title": "API Test",
        "goal": "test goal",
        "depth": "quick",
        "priority": "low",
    }
    r = await client.post("/api/v1/researches", json=payload)
    assert r.status_code in (200, 201)
    data = r.json()
    assert data["title"] == "API Test"
    assert "id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_list_researches(client):
    r = await client.get("/api/v1/researches?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Each item should have id, title, status
    for item in data:
        assert "id" in item
        assert "title" in item
        assert "status" in item


@pytest.mark.asyncio
async def test_dashboard(client):
    r = await client.get("/api/v1/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "stats" in data
    assert "recent" in data
    assert "popular" in data
    assert "agent" in data


@pytest.mark.asyncio
async def test_history_versions_empty(client):
    # First create a research
    payload = {"title": "H test", "goal": "g", "depth": "quick", "priority": "low"}
    r = await client.post("/api/v1/researches", json=payload)
    rid = r.json()["id"]

    r = await client.get(f"/api/v1/history/{rid}/versions")
    assert r.status_code == 200
    data = r.json()
    assert data["research_id"] == rid
    assert data["versions"] == []


@pytest.mark.asyncio
async def test_stuck_researches(client):
    r = await client.get("/api/v1/admin/stuck-researches")
    assert r.status_code == 200
    data = r.json()
    assert "stuck_count" in data
    assert "stuck" in data


@pytest.mark.asyncio
async def test_openai_compat_models(client):
    r = await client.get("/v1/models")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert len(data["data"]) >= 1
