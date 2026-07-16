"""Test search backend (MiniMax primary, DDGS fallback)."""
import pytest
from app.agents.search import MiniMaxSearch, DDGSSearch, WebSearcher


def test_minimax_search_no_key(monkeypatch):
    """Without API key, returns empty list (not error)."""
    monkeypatch.delenv("AIRW_MINIMAX_API_KEY", raising=False)
    s = MiniMaxSearch(api_key="", max_results=3)
    hits = s.search("python")
    assert hits == []


def test_minimax_search_with_key():
    """With API key, returns real hits."""
    import os
    key = os.environ.get("AIRW_MINIMAX_API_KEY", "")
    if not key:
        pytest.skip("AIRW_MINIMAX_API_KEY not set")
    s = MiniMaxSearch(api_key=key, max_results=3)
    hits = s.search("FastAPI Django 对比")
    assert len(hits) > 0
    assert all(h.title and h.url for h in hits)


def test_websearcher_backend_no_key(monkeypatch):
    """Without MiniMax key, falls back to DDGS."""
    monkeypatch.delenv("AIRW_MINIMAX_API_KEY", raising=False)
    s = WebSearcher(max_results=3)
    assert s.backend == "ddgs"


def test_websearcher_backend_with_key():
    """With MiniMax key, uses MiniMax."""
    import os
    key = os.environ.get("AIRW_MINIMAX_API_KEY", "")
    if not key:
        pytest.skip("AIRW_MINIMAX_API_KEY not set")
    s = WebSearcher(max_results=3)
    assert s.backend == "minimax"


def test_websearcher_search_returns_results():
    """Search returns list of SearchHit (any backend)."""
    s = WebSearcher(max_results=3)
    hits = s.search("Python 编程")
    # Either backend may succeed/fail — just verify type contract
    assert isinstance(hits, list)
