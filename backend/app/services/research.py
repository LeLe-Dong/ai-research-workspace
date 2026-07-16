from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Research, Review, Tag
from app.schemas.research import ResearchCreate


async def create_research(session: AsyncSession, data: ResearchCreate) -> Research:
    r = Research(
        title=data.title,
        goal=data.goal,
        constraints=data.constraints or "",
        expected_output=data.expected_output or "",
        depth=data.depth,
        priority=data.priority,
        estimated_cost=data.estimated_cost,
        status="pending",
    )
    session.add(r)
    await session.flush()

    # Attach tags if provided
    if data.tag_names:
        from app.services.tags import get_or_create_tag
        for name in data.tag_names:
            tag = await get_or_create_tag(session, name.strip().lower())
            from app.db.models import ResearchTag
            session.add(ResearchTag(research_id=r.id, tag_id=tag.id))

    await session.commit()
    # Eager-load tags relationship before returning
    from sqlalchemy.orm import selectinload
    await session.refresh(r, attribute_names=["tags"])
    return r


async def list_researches(session: AsyncSession, limit: int = 50) -> list[Research]:
    res = await session.execute(
        select(Research).order_by(Research.updated_at.desc()).limit(limit)
    )
    return list(res.scalars())


async def get_research_with_review(session: AsyncSession, research_id: str) -> tuple[Research, Review | None]:
    from sqlalchemy.orm import selectinload
    r = (await session.execute(
        select(Research)
        .options(selectinload(Research.tags))
        .where(Research.id == research_id)
    )).scalar_one_or_none()
    if r is None:
        return None, None
    review = (await session.execute(
        select(Review).where(Review.research_id == research_id)
    )).scalar_one_or_none()
    return r, review


async def delete_research(session: AsyncSession, research_id: str) -> bool:
    r = (await session.execute(
        select(Research).where(Research.id == research_id)
    )).scalar_one_or_none()
    if r is None:
        return False
    await session.delete(r)
    await session.commit()
    return True
