from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session_dep
from app.db.models import Research
from app.schemas.research import (
    ResearchCreate, ResearchDetail, ResearchSummary,
)
from app.services.research import (
    create_research, list_researches, get_research_with_review, delete_research,
)

router = APIRouter(prefix="/researches", tags=["researches"])


@router.post("", response_model=ResearchDetail, status_code=status.HTTP_201_CREATED)
async def create(payload: ResearchCreate, session: AsyncSession = Depends(get_session_dep)):
    r = await create_research(session, payload)
    return ResearchDetail.model_validate(r)


@router.get("", response_model=list[ResearchSummary])
async def list_all(
    session: AsyncSession = Depends(get_session_dep), 
    limit: int = 50,
    tag: str | None = None,  # Filter by tag name
):
    from sqlalchemy.orm import selectinload
    from app.db.models import Tag, ResearchTag
    
    query = (
        select(Research)
        .options(selectinload(Research.tags))
        .order_by(Research.updated_at.desc())
        .limit(limit)
    )
    
    if tag:
        # Filter by tag name
        tag_obj = (await session.execute(
            select(Tag).where(Tag.name == tag.strip().lower())
        )).scalar_one_or_none()
        if tag_obj:
            query = query.join(ResearchTag, Research.id == ResearchTag.research_id).where(
                ResearchTag.tag_id == tag_obj.id
            )
        else:
            # Tag not found - return empty
            return []
    
    rows = (await session.execute(query)).scalars().unique().all()
    return [
        ResearchSummary(
            id=r.id, title=r.title, status=r.status, priority=r.priority, depth=r.depth,
            score=8.4 if r.status == "completed" else None,
            tags=[{"id": t.id, "name": t.name, "color": t.color} for t in r.tags],
            created_at=r.created_at, updated_at=r.updated_at,
        ) for r in rows
    ]


@router.get("/{research_id}", response_model=ResearchDetail)
async def get_one(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    r, _ = await get_research_with_review(session, research_id)
    if r is None:
        raise HTTPException(404, "Research not found")
    return ResearchDetail.model_validate(r)


@router.delete("/{research_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    ok = await delete_research(session, research_id)
    if not ok:
        raise HTTPException(404, "Research not found")
    return None
