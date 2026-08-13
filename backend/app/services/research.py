from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Research, Review, Tag
from app.schemas.research import ResearchCreate


async def create_research(session: AsyncSession, data: ResearchCreate) -> Research:
    # If attaching to a topic, compute the next iteration number.
    topic_id = getattr(data, "topic_id", None) or None
    iteration = 1
    if topic_id:
        from sqlalchemy import func
        max_it = await session.execute(
            select(func.max(Research.iteration)).where(Research.topic_id == topic_id)
        )
        current_max = max_it.scalar()
        iteration = (current_max or 0) + 1

    r = Research(
        title=data.title,
        goal=data.goal,
        constraints=data.constraints or "",
        expected_output=data.expected_output or "",
        depth=data.depth,
        priority=data.priority,
        estimated_cost=data.estimated_cost,
        # Smart K8s validation trigger: -1=force off, 0=auto, 1=force on
        requires_k8s_validation=data.requires_k8s_validation,
        # Personalized research style (Phase A/B): when 1, the agent injects
        # the user's active (or specifically bound) KnowledgeStyle.
        use_custom_style=data.use_custom_style,
        style_id=data.style_id,
        topic_id=topic_id,
        iteration=iteration,
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
