"""Tag API: CRUD + attach/detach."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_session_dep
from app.db.models import Research, Tag
from app.services.tags import (
    list_tags, create_tag, get_or_create_tag,
    attach_tag, detach_tag, get_research_tags,
)

router = APIRouter(prefix="/tags", tags=["tags"])


class CreateTagRequest(BaseModel):
    name: str
    color: str = "blue"


class AttachTagRequest(BaseModel):
    tag_id: str | None = None  # attach existing tag by id
    name: str | None = None  # OR create + attach by name (idempotent)
    color: str = "blue"


@router.get("")
async def list_all_tags(session: AsyncSession = Depends(get_session_dep)):
    """List all tags with usage count."""
    from app.core.cache import tags_cache

    async def _compute():
        return await list_tags(session)

    tags = await tags_cache.get_or_set("all_tags", _compute, ttl=30.0)
    return {"tags": tags}


@router.post("")
async def create_new_tag(payload: CreateTagRequest, session: AsyncSession = Depends(get_session_dep)):
    """Create a new tag."""
    try:
        tag = await create_tag(session, payload.name, payload.color)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.post("/researches/{research_id}/attach")
async def attach_tag_to_research(
    research_id: str,
    payload: AttachTagRequest,
    session: AsyncSession = Depends(get_session_dep),
):
    """Attach a tag to a research (creates the tag if name is provided)."""
    # Check research exists
    r = (await session.execute(select(Research).where(Research.id == research_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "research not found")

    # Resolve tag
    if payload.tag_id:
        tag = (await session.execute(select(Tag).where(Tag.id == payload.tag_id))).scalar_one_or_none()
        if not tag:
            raise HTTPException(404, "tag not found")
    elif payload.name:
        try:
            tag = await get_or_create_tag(session, payload.name, payload.color)
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        raise HTTPException(400, "tag_id or name is required")

    attached = await attach_tag(session, research_id, tag.id)
    # Invalidate cache
    from app.core.cache import tags_cache
    tags_cache.invalidate("all_tags")
    return {
        "attached": attached,
        "tag": {"id": tag.id, "name": tag.name, "color": tag.color},
        "research_id": research_id,
    }


@router.post("/researches/{research_id}/detach")
async def detach_tag_from_research(
    research_id: str,
    tag_id: str = Query(..., description="tag to detach"),
    session: AsyncSession = Depends(get_session_dep),
):
    """Detach a tag from a research."""
    removed = await detach_tag(session, research_id, tag_id)
    # Invalidate cache
    from app.core.cache import tags_cache
    tags_cache.invalidate("all_tags")
    return {"removed": removed, "tag_id": tag_id, "research_id": research_id}


@router.get("/researches/{research_id}")
async def get_tags_for_research(
    research_id: str, session: AsyncSession = Depends(get_session_dep)
):
    """Get all tags for a research."""
    return {"tags": await get_research_tags(session, research_id)}
