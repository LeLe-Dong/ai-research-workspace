"""OpenAI-compatible API for the AI Research Workspace.

Exposes:
  POST /v1/researches   — alias for /api/v1/researches (create)
  POST /v1/runs          — start a research job
  GET  /v1/runs/{id}     — get status + artifacts
  GET  /v1/runs/{id}/events — SSE stream of timeline events

This is intentionally minimal: we expose enough to integrate external tools
(including hermes agent itself, MCP clients, scripts) without committing to
the full OpenAI Assistants API.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.v1.stream import _fetch_state, _sse
from app.db.database import get_session
from app.db.models import Research, TimelineEvent

logger = logging.getLogger(__name__)
router = APIRouter()  # Routes use explicit /v1 prefix  # Mounted under /api/v1, so /v1 here would collide


class ResearchRequest(BaseModel):
    title: str = Field(..., max_length=200)
    goal: str
    constraints: str = ""
    expected_output: str = ""
    depth: str = "standard"
    priority: str = "medium"
    estimated_cost: float = 0.0


@router.post("/v1/researches")
async def openai_create_research(req: ResearchRequest):
    """Create a new research (OpenAI-compatible shape: input fields → id)."""
    from app.agents import get_agent_client
    from app.services.research import create_research
    from app.schemas.research import ResearchCreate
    from app.db.database import get_session

    async with get_session() as session:
        data = ResearchCreate(
            title=req.title,
            goal=req.goal,
            constraints=req.constraints,
            expected_output=req.expected_output,
            depth=req.depth,
            priority=req.priority,
            estimated_cost=req.estimated_cost,
        )
        research = await create_research(session, data)
        return {
            "id": research.id,
            "object": "research",
            "created_at": research.created_at.isoformat(),
            "status": research.status,
        }


@router.post("/v1/runs")
async def start_run(payload: dict):
    """Start a research job. Returns immediately with run_id.

    payload: {"research_id": "..."} OR {"research": {...}} to create inline
    """
    research_id = payload.get("research_id")
    if not research_id and "research" in payload:
        # Inline create
        r = payload["research"]
        from app.schemas.research import ResearchCreate
        from app.db.database import get_session
        from app.services.research import create_research
        async with get_session() as session:
            data = ResearchCreate(
                title=r["title"], goal=r["goal"],
                constraints=r.get("constraints", ""),
                expected_output=r.get("expected_output", ""),
                depth=r.get("depth", "standard"),
                priority=r.get("priority", "medium"),
                estimated_cost=r.get("estimated_cost", 0.0),
            )
            research = await create_research(session, data)
            research_id = research.id

    if not research_id:
        raise HTTPException(400, "research_id or research object required")

    async with get_session() as session:
        r = (await session.execute(
            select(Research).where(Research.id == research_id)
        )).scalar_one_or_none()
        if not r:
            raise HTTPException(404, f"research {research_id} not found")
        if r.status not in ("pending", "failed"):
            raise HTTPException(400, f"research is {r.status}, can only start from pending or failed")

    from app.services.executor import run_research_job
    asyncio.create_task(run_research_job(research_id))
    return {
        "id": f"run_{research_id}",
        "research_id": research_id,
        "object": "run",
        "status": "started",
        "created_at": datetime.utcnow().isoformat(),
    }


@router.get("/v1/runs/{run_id}")
async def get_run(run_id: str):
    """Get run status."""
    research_id = run_id.removeprefix("run_")
    async with get_session() as session:
        r = (await session.execute(
            select(Research).where(Research.id == research_id)
        )).scalar_one_or_none()
        if not r:
            raise HTTPException(404, f"research {research_id} not found")

    # Get latest task/event counts
    tasks = (await session.execute(
        select(TimelineEvent).where(TimelineEvent.research_id == research_id)
    )).scalars().all()

    return {
        "id": run_id,
        "research_id": research_id,
        "status": r.status,
        "title": r.title,
        "events": len(tasks),
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


@router.get("/v1/runs/{run_id}/events")
async def stream_run_events(run_id: str, since: int = 0):
    """SSE stream of research timeline events (OpenAI-style incremental updates)."""
    research_id = run_id.removeprefix("run_")
    last_seq = since

    async def gen():
        nonlocal last_seq
        async with get_session() as session:
            r = (await session.execute(
                select(Research).where(Research.id == research_id)
            )).scalar_one_or_none()
            if not r:
                yield _sse({"type": "error", "message": f"research {research_id} not found"})
                return

        for _ in range(20):
            snap = await _fetch_state(research_id, last_seq)
            if "error" in snap:
                yield _sse({"type": "error", "message": snap["error"]})
                return
            if snap.get("status") != "pending" or snap.get("events") or snap.get("tasks"):
                break
            await asyncio.sleep(0.25)

        snap = await _fetch_state(research_id, last_seq)
        if "error" in snap:
            yield _sse({"type": "error", "message": snap["error"]})
            return

        for evt in snap["events"]:
            yield _sse({"type": "timeline", "event": evt, "object": "timeline.event"})
            last_seq = max(last_seq, evt["sequence"])
        for art in snap["artifacts"]:
            yield _sse({"type": "artifact", "artifact": art, "object": "artifact"})
        for t in snap["tasks"]:
            yield _sse({"type": "task", "task": t, "object": "task"})

        while True:
            snap = await _fetch_state(research_id, last_seq)
            if "error" in snap:
                yield _sse({"type": "error", "message": snap["error"]})
                return
            new_events = [e for e in snap["events"] if e["sequence"] > last_seq]
            for evt in new_events:
                yield _sse({"type": "timeline", "event": evt, "object": "timeline.event"})
                last_seq = max(last_seq, evt["sequence"])
            for art in snap["artifacts"]:
                already = snap.get("emitted_artifact_ids", set())
                if art["id"] not in already:
                    yield _sse({"type": "artifact", "artifact": art, "object": "artifact"})
            if snap.get("status") in ("completed", "failed"):
                yield _sse({"type": "end", "status": snap["status"]})
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                     "X-Accel-Buffering": "no",
                                     "Connection": "keep-alive"})


@router.get("/v1/models")
async def list_models():
    """List available agents as if they were models."""
    from app.core.config import settings
    return {
        "object": "list",
        "data": [
            {"id": "mock", "object": "model", "owned_by": "airw", "description": "固定剧本演示模式"},
            {"id": "llm", "object": "model", "owned_by": "airw",
             "description": "LLM 模型 — 由 /api/v1/config/llm 提供 provider/base_url/model/api_key（兼容 OpenAI 协议：stepfun / minimax / kimi / openai_compat）"},
            {"id": "hermes-researcher", "object": "model", "owned_by": "airw",
             "description": "Hermes 预研专家 - 14 维度框架"},
        ],
        "current_mode": settings.agent_mode,
    }
