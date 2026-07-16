"""Test executor: end-to-end research execution with mock agent."""
import pytest
import asyncio
from app.db.database import init_db
from app.services.executor import run_research_job
from app.services.research import list_researches, get_research_with_review
from app.services import executor as executor_module
from app.db.models import Research, ResearchVersion
from sqlalchemy import select


@pytest.fixture
async def fresh_db():
    """Reset DB before each test."""
    await init_db()
    yield


@pytest.mark.asyncio
async def test_executor_runs_mock_research_to_completion(fresh_db, monkeypatch):
    """End-to-end: create research → run executor → completed status + artifacts."""
    from app.db.database import get_session
    
    # Mock asyncio timeout to be no-op (don't timeout tests)
    class FakeTimeout:
        def __init__(self, delay): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
    monkeypatch.setattr(executor_module.asyncio, "timeout", lambda *a, **kw: FakeTimeout(None))
    
    # Create a research
    from app.schemas.research import ResearchCreate
    async with get_session() as session:
        r = Research(
            id="test_exec_001",
            title="Test research",
            goal="Test goal",
            depth="quick",
            priority="low",
            estimated_cost=1.0,
        )
        session.add(r)
        await session.commit()
    
    # Run executor
    await run_research_job("test_exec_001")
    
    # Verify completed
    async with get_session() as session:
        from app.db.database import get_session as gs
        r = (await session.execute(
            select(Research).where(Research.id == "test_exec_001")
        )).scalar_one()
        assert r.status == "completed"
        # Mock should produce artifacts
        from app.db.models import Artifact
        arts = (await session.execute(
            select(Artifact).where(Artifact.research_id == "test_exec_001")
        )).scalars().all()
        assert len(arts) >= 1


@pytest.mark.asyncio
async def test_executor_records_version_after_completion(fresh_db, monkeypatch):
    """After execution, a new ResearchVersion is created."""
    from app.db.database import get_session
    
    class FakeTimeout:
        def __init__(self, delay): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
    monkeypatch.setattr(executor_module.asyncio, "timeout", lambda *a, **kw: FakeTimeout(None))
    
    from app.schemas.research import ResearchCreate
    async with get_session() as session:
        r = Research(
            id="test_exec_002",
            title="Version test",
            goal="Test version",
            depth="quick",
            priority="low",
            estimated_cost=1.0,
        )
        session.add(r)
        await session.commit()
    
    await run_research_job("test_exec_002")
    
    async with get_session() as session:
        versions = (await session.execute(
            select(ResearchVersion).where(ResearchVersion.research_id == "test_exec_002")
        )).scalars().all()
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].status == "completed"


@pytest.mark.asyncio
async def test_executor_handles_missing_research_gracefully(fresh_db, monkeypatch):
    """If research doesn't exist, executor doesn't crash."""
    class FakeTimeout:
        def __init__(self, delay): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
    monkeypatch.setattr(executor_module.asyncio, "timeout", lambda *a, **kw: FakeTimeout(None))
    
    # Should not raise
    await run_research_job("nonexistent_id_xxxxx")
