"""Start / inspect a research execution."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session_dep
from app.db.models import Research
from app.services.executor import run_research_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/researches", tags=["execute"])

# Per-research asyncio locks to prevent concurrent starts
# Using dict (not set) so we can await the lock if it's held
_locks: dict[str, asyncio.Lock] = {}


def _get_lock(research_id: str) -> asyncio.Lock:
    """Get or create a lock for the given research_id."""
    if research_id not in _locks:
        _locks[research_id] = asyncio.Lock()
    return _locks[research_id]


@router.post("/{research_id}/start", status_code=202)
async def start(
    research_id: str,
    force: bool = False,
    session: AsyncSession = Depends(get_session_dep),
):
    r = (await session.execute(select(Research).where(Research.id == research_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Research not found")
    if r.status == "running" and not force:
        return {"status": "already_running", "research_id": research_id}
    if r.status == "running" and force:
        # Force-restart: likely a ghost (uvicorn restarted, asyncio task died but DB stuck)
        r.status = "pending"
        r.error_message = "强制重启 (前次执行失联)"
        await session.commit()
    if r.status == "completed":
        # Allow re-run by resetting status; user can press "Run again"
        r.status = "pending"
        await session.commit()

    lock = _get_lock(research_id)

    # If lock is already held, another start is in flight
    if lock.locked():
        return {"status": "already_started", "research_id": research_id}

    async def _wrap():
        async with lock:
            try:
                # Timeout scales with research depth. Deep research with an
                # LLM-driven k8s experiment (many long assertions) can exceed
                # the 30 min default, so give deep/standard runs more headroom.
                depth = r.depth or "standard"
                needs_k8s = bool(getattr(r, "requires_k8s_validation", 0) == 1)
                if depth == "deep":
                    timeout = 3600 if needs_k8s else 2700
                elif depth == "standard":
                    timeout = 2700 if needs_k8s else 1800
                else:  # quick
                    timeout = 1800 if needs_k8s else 900
                await run_research_job(research_id, timeout_sec=timeout)
            except Exception as e:
                logger.exception(f"run_research_job failed for {research_id}")
                # Mark as failed so it doesn't appear stuck
                from app.db.database import get_session
                async with get_session() as err_session:
                    err_r = (await err_session.execute(
                        select(Research).where(Research.id == research_id)
                    )).scalar_one_or_none()
                    if err_r and err_r.status == "running":
                        err_r.status = "failed"
                        await err_session.commit()

    asyncio.create_task(_wrap())
    return {"status": "started", "research_id": research_id}
