"""Tag service: CRUD, attach/detach to research."""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Tag, ResearchTag, Research


async def list_tags(session: AsyncSession) -> list[dict]:
    """List all tags with research count."""
    result = await session.execute(
        select(Tag, func.count(ResearchTag.research_id).label("count"))
        .outerjoin(ResearchTag, Tag.id == ResearchTag.tag_id)
        .group_by(Tag.id)
        .order_by(func.count(ResearchTag.research_id).desc(), Tag.name)
    )
    rows = result.all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "color": t.color,
            "count": count,
        }
        for t, count in rows
    ]


async def get_or_create_tag(session: AsyncSession, name: str, color: str = "blue") -> Tag:
    """Get existing tag by name, or create new one."""
    result = await session.execute(select(Tag).where(Tag.name == name))
    tag = result.scalar_one_or_none()
    if tag:
        return tag
    tag = Tag(name=name, color=color)
    session.add(tag)
    await session.flush()
    return tag


async def create_tag(session: AsyncSession, name: str, color: str = "blue") -> Tag:
    """Create a new tag. Raises if name already exists."""
    name = name.strip().lower()
    if not name:
        raise ValueError("tag name cannot be empty")
    if len(name) > 50:
        raise ValueError("tag name too long (max 50)")

    result = await session.execute(select(Tag).where(Tag.name == name))
    if result.scalar_one_or_none():
        raise ValueError(f"tag '{name}' already exists")

    tag = Tag(name=name, color=color)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


async def attach_tag(session: AsyncSession, research_id: str, tag_id: str) -> bool:
    """Attach a tag to a research. Returns True if newly attached."""
    # Check if already attached
    existing = (await session.execute(
        select(ResearchTag).where(
            ResearchTag.research_id == research_id,
            ResearchTag.tag_id == tag_id,
        )
    )).scalar_one_or_none()
    if existing:
        return False
    rt = ResearchTag(research_id=research_id, tag_id=tag_id)
    session.add(rt)
    await session.commit()
    return True


async def detach_tag(session: AsyncSession, research_id: str, tag_id: str) -> bool:
    """Detach a tag from a research. Returns True if removed."""
    existing = (await session.execute(
        select(ResearchTag).where(
            ResearchTag.research_id == research_id,
            ResearchTag.tag_id == tag_id,
        )
    )).scalar_one_or_none()
    if not existing:
        return False
    await session.delete(existing)
    await session.commit()
    return True


async def get_research_tags(session: AsyncSession, research_id: str) -> list[dict]:
    """Get all tags attached to a research."""
    result = await session.execute(
        select(Tag).join(ResearchTag, Tag.id == ResearchTag.tag_id)
        .where(ResearchTag.research_id == research_id)
        .order_by(Tag.name)
    )
    tags = result.scalars().all()
    return [{"id": t.id, "name": t.name, "color": t.color} for t in tags]
