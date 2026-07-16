"""Test history service version creation and diff."""
import pytest
import asyncio
from app.db.database import init_db, get_session
from app.db.models import Research, ResearchVersion, Artifact
from app.services.history import record_version, get_versions, diff_versions, fork_version


@pytest.mark.asyncio
async def test_record_version_first_time():
    """Test recording a version for a new research creates v1."""
    await init_db()
    async with get_session() as session:
        r = Research(
            id="test1",
            title="Test Research",
            goal="test goal",
            depth="quick",
            priority="low",
            status="completed",
        )
        session.add(r)
        await session.commit()

        v = await record_version(session, r, commit_message="test")
        await session.commit()
        assert v.version == 1
        assert v.parent_version is None
        assert v.commit_message == "test"


@pytest.mark.asyncio
async def test_record_version_handles_multiple_artifacts():
    """Test that record_version doesn't crash when multiple markdown artifacts exist (regression test)."""
    await init_db()
    async with get_session() as session:
        r = Research(
            id="test2",
            title="Test Rerun",
            goal="test rerun",
            depth="quick",
            priority="low",
            status="completed",
        )
        session.add(r)
        await session.flush()

        # Add 3 markdown artifacts (simulating multiple reruns)
        for i in range(3):
            session.add(Artifact(
                research_id=r.id,
                kind="markdown",
                title=f"Report v{i+1}",
                content=f"Report content {i+1}",
                version=1,
            ))
        await session.commit()

        # This should NOT raise MultipleResultsFound
        v = await record_version(session, r, commit_message="rerun")
        await session.commit()
        assert v.version == 1
        # Should pick the latest artifact (highest created_at)
        assert "Report content 3" in v.report_markdown


@pytest.mark.asyncio
async def test_get_versions_sorted_desc():
    """Test versions are returned in descending order."""
    await init_db()
    async with get_session() as session:
        r = Research(id="test3", title="T", goal="g", depth="quick", priority="low", status="completed")
        session.add(r)
        await session.flush()

        # Add 3 versions
        for i in range(1, 4):
            from app.services.history import record_version
            v = await record_version(session, r, commit_message=f"v{i}")
            await session.commit()
            assert v.version == i

        versions = await get_versions(session, r.id)
        assert len(versions) == 3
        # First should be highest version
        assert versions[0]["version"] == 3
        assert versions[-1]["version"] == 1


@pytest.mark.asyncio
async def test_diff_detects_field_changes():
    """Test diff correctly identifies field changes between versions."""
    await init_db()
    async with get_session() as session:
        r1 = Research(id="test4", title="v1 title", goal="v1 goal", depth="quick", priority="low", status="completed")
        session.add(r1)
        await session.flush()
        await record_version(session, r1, commit_message="v1")
        await session.commit()

        r2 = Research(id="test5", title="v2 title", goal="v2 goal", depth="deep", priority="high", status="completed")
        session.add(r2)
        await session.flush()
        await record_version(session, r2, commit_message="v2")
        await session.commit()

        # These are different researches - we need to test on same research
        # So test with same research having 2 versions
        r3 = Research(id="test6", title="orig", goal="orig goal", depth="quick", priority="low", status="completed")
        session.add(r3)
        await session.flush()
        await record_version(session, r3, commit_message="v1")
        await session.commit()

        # Modify and create v2
        r3.title = "new title"
        r3.goal = "new goal"
        await session.commit()
        await record_version(session, r3, commit_message="v2")
        await session.commit()

        diff = await diff_versions(session, r3.id, 1, 2)
        assert diff["changed"] is True
        fields = {d["field"] for d in diff["field_diffs"]}
        assert "title" in fields
        assert "goal" in fields


@pytest.mark.asyncio
async def test_fork_creates_new_research():
    """Test fork creates a new research from a historical version."""
    await init_db()
    async with get_session() as session:
        r = Research(
            id="test7",
            title="Original",
            goal="original goal",
            depth="standard",
            priority="medium",
            estimated_cost=10.0,
            status="completed",
        )
        session.add(r)
        await session.flush()
        await record_version(session, r, commit_message="v1")
        await session.commit()

        # Fork
        new_r = await fork_version(session, r.id, 1, commit_message="my fork")
        assert new_r.id != r.id
        assert "(fork v1)" in new_r.title
        assert new_r.status == "pending"
        assert new_r.goal == "original goal"
        assert new_r.estimated_cost == 10.0

        # The new research should have a v1 version
        versions = await get_versions(session, new_r.id)
        assert len(versions) == 1
        assert versions[0]["version"] == 1
        assert versions[0]["created_by"] == "fork"
