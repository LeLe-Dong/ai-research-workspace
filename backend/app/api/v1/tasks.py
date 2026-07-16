"""Read-only task + timeline + artifacts + review queries for one research."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session_dep
from app.db.models import Artifact, Research, Review, Task, TimelineEvent
from app.schemas.research import (
    ArtifactOut, ReviewOut, TaskNode, TimelineEventOut,
)

router = APIRouter(prefix="/researches", tags=["tasks"])


async def _ensure(session: AsyncSession, research_id: str) -> Research:
    r = (await session.execute(select(Research).where(Research.id == research_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Research not found")
    return r


@router.get("/{research_id}/tasks", response_model=list[TaskNode])
async def list_tasks(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    await _ensure(session, research_id)
    rows = (await session.execute(
        select(Task).where(Task.research_id == research_id).order_by(Task.order_index)
    )).scalars().all()
    return [TaskNode.model_validate(t) for t in rows]


@router.get("/{research_id}/timeline", response_model=list[TimelineEventOut])
async def list_timeline(research_id: str, since: int = 0,
                       session: AsyncSession = Depends(get_session_dep)):
    """since: only return events with sequence > since (for SSE catch-up)."""
    await _ensure(session, research_id)
    rows = (await session.execute(
        select(TimelineEvent)
        .where(TimelineEvent.research_id == research_id, TimelineEvent.sequence > since)
        .order_by(TimelineEvent.sequence)
    )).scalars().all()
    return [TimelineEventOut.model_validate(e) for e in rows]


@router.get("/{research_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    await _ensure(session, research_id)
    rows = (await session.execute(
        select(Artifact).where(Artifact.research_id == research_id).order_by(Artifact.created_at)
    )).scalars().all()
    return [ArtifactOut.model_validate(a) for a in rows]


@router.get("/{research_id}/review", response_model=ReviewOut | None)
async def get_review(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    await _ensure(session, research_id)
    r = (await session.execute(
        select(Review).where(Review.research_id == research_id)
    )).scalar_one_or_none()
    if r is None:
        return None
    return ReviewOut.model_validate(r)
