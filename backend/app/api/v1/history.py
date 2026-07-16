"""History API: versions, diff, fork."""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db.database import get_session_dep
from app.db.models import Research, ResearchVersion
from app.services.history import get_versions, get_version_detail, diff_versions, fork_version, record_version

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/{research_id}/versions")
async def list_versions(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    """List all versions for a research."""
    result = await session.execute(select(Research).where(Research.id == research_id))
    research = result.scalar_one_or_none()
    if not research:
        raise HTTPException(404, "research not found")
    return {"research_id": research_id, "versions": await get_versions(session, research_id)}


@router.get("/{research_id}/versions/{version}")
async def get_version(research_id: str, version: int, session: AsyncSession = Depends(get_session_dep)):
    """Get a single version snapshot."""
    v = await get_version_detail(session, research_id, version)
    if not v:
        raise HTTPException(404, f"version {version} not found")
    return v


@router.get("/{research_id}/diff")
async def diff_versions_api(
    research_id: str,
    v1: int = Query(..., description="Base version"),
    v2: int = Query(..., description="Compare version"),
    session: AsyncSession = Depends(get_session_dep),
):
    """Diff two versions."""
    try:
        result = await diff_versions(session, research_id, v1, v2)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return result


@router.post("/{research_id}/fork")
async def fork_version_api(
    research_id: str,
    version: int = Query(..., description="Version to fork from"),
    commit_message: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """Fork a research from a historical version."""
    result = await session.execute(select(Research).where(Research.id == research_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "research not found")
    try:
        new_research = await fork_version(session, research_id, version, commit_message)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {
        "id": new_research.id,
        "title": new_research.title,
        "status": new_research.status,
        "forked_from": f"{research_id}@{version}",
    }


@router.post("/{research_id}/rollback")
async def rollback_version_api(
    research_id: str,
    version: int = Query(..., description="Version to rollback to"),
    commit_message: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """Rollback by forking from a historical version (non-destructive)."""
    return await fork_version_api(research_id, version, commit_message or f"Rollback to v{version}", session)

