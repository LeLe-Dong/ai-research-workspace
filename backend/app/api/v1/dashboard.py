from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session, get_session_dep
from app.schemas.dashboard import DashboardData, DashboardStats, RecentResearch, PopularKnowledge, AgentStatus
from app.services.dashboard import get_stats, get_recent_researches, get_popular_knowledge, get_agent_status

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardData)
async def dashboard(session: AsyncSession = Depends(get_session_dep)):
    from app.core.cache import dashboard_cache

    async def _compute():
        stats = await get_stats(session)
        recent_rows = await get_recent_researches(session)
        popular = await get_popular_knowledge(session)
        agent = await get_agent_status(session)
        return stats, recent_rows, popular, agent

    stats, recent_rows, popular, agent = await dashboard_cache.get_or_set(
        "dashboard", _compute, ttl=5.0
    )
    return DashboardData(
        stats=DashboardStats(**stats),
        recent=[
            RecentResearch(
                id=r.id, title=r.title, status=r.status, priority=r.priority, depth=r.depth,
                score=8.4, updated_at=r.updated_at,
            ) for r in recent_rows
        ],
        popular=[PopularKnowledge(**p) for p in popular],
        agent=AgentStatus(**agent),
    )
