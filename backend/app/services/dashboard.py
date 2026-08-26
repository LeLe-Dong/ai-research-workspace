from datetime import datetime, timedelta
import random

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Research, Artifact, TimelineEvent, Review


async def get_stats(session: AsyncSession) -> dict:
    """Get all stats in 2 queries instead of 4 (uses index on status)."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Single aggregated query: count by status + today
    from sqlalchemy import case
    rows = (await session.execute(
        select(
            func.count(Research.id).label("total"),
            func.sum(case((Research.status == "completed", 1), else_=0)).label("completed"),
            func.sum(case((Research.status == "running", 1), else_=0)).label("running"),
            func.sum(case(
                ((Research.status == "completed") & (Research.updated_at >= today_start), 1),
                else_=0
            )).label("today_done"),
        )
    )).one()
    
    total = rows.total or 0
    completed = rows.completed or 0
    running = rows.running or 0
    today_done = rows.today_done or 0

    # Average score from actual reviews (fallback to 0.0 if no reviews yet)
    avg_result = (await session.execute(
        select(func.avg(Review.overall_score))
    )).scalar()
    avg_score = round(avg_result, 1) if avg_result else 0.0

    # KB count = number of completed researches (each has at least 1 markdown artifact)
    kb_count = completed

    return {
        "total_researches": total,
        "completed": completed,
        "running": running,
        "today_completed": today_done,
        "average_score": avg_score,
        "kb_count": kb_count,
    }


async def get_recent_researches(session: AsyncSession, limit: int = 5) -> list[Research]:
    from sqlalchemy.orm import selectinload
    res = await session.execute(
        select(Research)
        .options(selectinload(Research.tags))
        .order_by(Research.updated_at.desc())
        .limit(limit)
    )
    return list(res.scalars())


async def get_popular_knowledge(session: AsyncSession, limit: int = 4) -> list[dict]:
    """Aggregate markdown artifacts from completed researches as KB items."""
    res = await session.execute(
        select(Research, Artifact)
        .join(Artifact, Artifact.research_id == Research.id)
        .where(Artifact.kind == "markdown", Research.status == "completed")
        .order_by(Research.updated_at.desc())
        .limit(limit)
    )
    rows = res.all()
    items = []
    for r, a in rows:
        # Fetch actual review score for this research
        rv = (await session.execute(
            select(Review.overall_score).where(Review.research_id == r.id)
        )).scalar()
        items.append({
            "id": a.id,
            "research_id": r.id,
            "title": a.title,
            "excerpt": a.content.split("\n")[2][:140] if len(a.content.split("\n")) > 2 else "",
            "tags": [r.priority, r.depth],
            "score": round(rv, 1) if rv else None,
            "updated_at": r.updated_at,
        })
    return items


async def get_agent_status(session: AsyncSession) -> dict:
    last_event = (await session.execute(
        select(TimelineEvent).order_by(TimelineEvent.ts.desc()).limit(1)
    )).scalar_one_or_none()
    return {
        "engine": "Hermes Engine",
        "mode": "mock",
        "version": "v0.1",
        "online": True,
        "last_active": last_event.ts.isoformat() if last_event else None,
    }
