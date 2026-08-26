from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session, get_session_dep
from app.schemas.dashboard import DashboardData, DashboardStats, RecentResearch, PopularKnowledge, AgentStatus
from app.services.dashboard import get_stats, get_recent_researches, get_popular_knowledge, get_agent_status

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardData)
async def dashboard(session: AsyncSession = Depends(get_session_dep)):
    from app.core.cache import dashboard_cache
    from sqlalchemy import select
    from app.db.models import Review

    async def _compute():
        stats = await get_stats(session)
        recent_rows = await get_recent_researches(session)
        popular = await get_popular_knowledge(session)
        agent = await get_agent_status(session)

        # Batch-fetch scores for all recent researches in one query
        recent_ids = [r.id for r in recent_rows]
        scores_map: dict[str, float] = {}
        if recent_ids:
            rv_rows = (await session.execute(
                select(Review.research_id, Review.overall_score)
                .where(Review.research_id.in_(recent_ids))
            )).all()
            scores_map = {rid: sc for rid, sc in rv_rows}

        return stats, recent_rows, popular, agent, scores_map

    stats, recent_rows, popular, agent, scores_map = await dashboard_cache.get_or_set(
        "dashboard", _compute, ttl=5.0
    )
    return DashboardData(
        stats=DashboardStats(**stats),
        recent=[
            RecentResearch(
                id=r.id, title=r.title, status=r.status, priority=r.priority, depth=r.depth,
                score=round(scores_map.get(r.id, 0.0), 1) if r.status == "completed" else None,
                updated_at=r.updated_at,
            ) for r in recent_rows
        ],
        popular=[PopularKnowledge(**p) for p in popular],
        agent=AgentStatus(**agent),
    )
