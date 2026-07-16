"""Test tag CRUD + attach/detach."""
import pytest
from app.db.database import init_db, get_session
from app.db.models import Research, Tag, ResearchTag
from app.services.tags import (
    list_tags, create_tag, get_or_create_tag,
    attach_tag, detach_tag, get_research_tags,
)


@pytest.mark.asyncio
async def test_create_and_list_tags():
    """Test creating tags and listing with count."""
    await init_db()
    async with get_session() as session:
        t1 = await create_tag(session, "python")
        t2 = await create_tag(session, "rust", color="red")
        assert t1.name == "python"
        assert t1.color == "blue"
        assert t2.color == "red"

        tags = await list_tags(session)
        assert len(tags) == 2
        # Both should have count=0
        assert all(t["count"] == 0 for t in tags)


@pytest.mark.asyncio
async def test_create_tag_validation():
    """Test tag name validation."""
    await init_db()
    async with get_session() as session:
        # Empty name should fail
        with pytest.raises(ValueError, match="cannot be empty"):
            await create_tag(session, "  ")
        # Too long should fail
        with pytest.raises(ValueError, match="too long"):
            await create_tag(session, "x" * 60)


@pytest.mark.asyncio
async def test_duplicate_tag_rejected():
    """Test creating a tag with same name fails."""
    await init_db()
    async with get_session() as session:
        await create_tag(session, "duplicate")
        with pytest.raises(ValueError, match="already exists"):
            await create_tag(session, "duplicate")
        # Case insensitive
        with pytest.raises(ValueError, match="already exists"):
            await create_tag(session, "DUPLICATE")


@pytest.mark.asyncio
async def test_get_or_create_idempotent():
    """Test get_or_create_tag is idempotent."""
    await init_db()
    async with get_session() as session:
        t1 = await get_or_create_tag(session, "new")
        await session.commit()
        t2 = await get_or_create_tag(session, "new")
        # Same id
        assert t1.id == t2.id


@pytest.mark.asyncio
async def test_attach_and_detach_tag():
    """Test attaching and detaching tags to research."""
    await init_db()
    async with get_session() as session:
        r = Research(id="r1", title="T", goal="g", depth="quick", priority="low", status="pending")
        session.add(r)
        await session.commit()

        tag = await create_tag(session, "test")
        attached = await attach_tag(session, r.id, tag.id)
        assert attached is True

        # Re-attach should return False (idempotent)
        attached2 = await attach_tag(session, r.id, tag.id)
        assert attached2 is False

        # Get tags for research
        tags = await get_research_tags(session, r.id)
        assert len(tags) == 1
        assert tags[0]["name"] == "test"

        # List should show count=1
        all_tags = await list_tags(session)
        assert any(t["name"] == "test" and t["count"] == 1 for t in all_tags)

        # Detach
        removed = await detach_tag(session, r.id, tag.id)
        assert removed is True

        tags_after = await get_research_tags(session, r.id)
        assert len(tags_after) == 0

        # Re-detach should return False
        removed2 = await detach_tag(session, r.id, tag.id)
        assert removed2 is False


@pytest.mark.asyncio
async def test_create_research_with_tag_names():
    """Test creating a research auto-attaches tags."""
    await init_db()
    async with get_session() as session:
        from app.services.research import create_research
        from app.schemas.research import ResearchCreate

        data = ResearchCreate(
            title="Tagged research",
            goal="test",
            tag_names=["alpha", "beta", "gamma"],
        )
        r = await create_research(session, data)
        assert r.id is not None

        # Check tags were attached
        tags = await get_research_tags(session, r.id)
        tag_names = {t["name"] for t in tags}
        assert tag_names == {"alpha", "beta", "gamma"}
