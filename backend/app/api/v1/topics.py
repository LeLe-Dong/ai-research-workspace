"""Research Topics API — iterative research baseline.

A topic aggregates multiple research runs on the same subject. Each round
is a Research row (topic_id + iteration). Endpoints:

  GET    /api/v1/topics                 — list topics (+ iteration stats)
  POST   /api/v1/topics                 — create a topic
  GET    /api/v1/topics/{id}            — topic detail + iterations timeline
  DELETE /api/v1/topics/{id}            — delete topic (+ its researches)
  POST   /api/v1/topics/{id}/iterate    — launch the next iteration, carrying
                                          forward/adjusting the research
                                          boundary from the latest round
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session_dep
from app.db.models import Research, ResearchTopic
from app.services.history import record_version

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/topics", tags=["topics"])


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class IterateRequest(BaseModel):
    """Boundary adjustments for the next iteration.

    All optional: unset fields are carried forward from the latest round.
    """
    goal: str | None = None
    constraints: str | None = None
    expected_output: str | None = None
    depth: str | None = None
    priority: str | None = None
    commit_message: str = ""  # what changed this round / why


def _topic_out(t: ResearchTopic, sessions: list[dict]) -> dict:
    completed = sum(1 for s in sessions if s["status"] == "completed")
    latest = sessions[-1] if sessions else None

    # Baseline metrics — the first round is the reference point; later
    # iterations are judged against it.
    baseline_score = None
    baseline_goal = ""
    if sessions:
        first = sessions[0]
        baseline_score = first.get("score")
        baseline_goal = first.get("goal") or ""

    scored = [s for s in sessions if s.get("score") is not None]
    avg_score = round(sum(s["score"] for s in scored) / len(scored), 2) if scored else None
    best = max(scored, key=lambda s: s["score"]) if scored else None
    score_trend = [s.get("score") for s in sessions]  # per-iteration scores
    latest_score = latest.get("score") if latest else None
    delta_from_baseline = None
    if latest_score is not None and baseline_score is not None:
        delta_from_baseline = round(latest_score - baseline_score, 2)

    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "iteration_count": len(sessions),
        "completed_count": completed,
        "latest_status": (latest or {}).get("status"),
        "latest_score": latest_score,
        "latest_title": (latest or {}).get("title"),
        # Baseline & trend
        "baseline": {
            "score": baseline_score,
            "goal": baseline_goal[:200],
            "iteration": 1,
        },
        "score_trend": score_trend,
        "avg_score": avg_score,
        "best_iteration": best.get("iteration") if best else None,
        "best_score": best.get("score") if best else None,
        "delta_from_baseline": delta_from_baseline,
        "improved": (delta_from_baseline or 0) > 0,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


async def _research_out(session: AsyncSession, r: Research) -> dict:
    """Build a research summary for a topic timeline, including the review
    score, a report excerpt, and a k8s-experiment result summary so the UI
    can show what each iteration concluded and measured."""
    score = None
    report_excerpt = ""
    k8s_summary = ""

    # Review score
    from app.db.models import Review
    rev = (await session.execute(
        select(Review).where(Review.research_id == r.id)
    )).scalar_one_or_none()
    if rev is not None:
        score = rev.overall_score

    # Report excerpt (markdown artifact)
    from app.db.models import Artifact
    md = (await session.execute(
        select(Artifact).where(
            Artifact.research_id == r.id, Artifact.kind == "markdown"
        ).order_by(Artifact.id.desc()).limit(1)
    )).scalar_one_or_none()
    if md is not None:
        report_excerpt = (md.content or "").strip()[:300]

    # k8s experiment result summary
    exp = (await session.execute(
        select(Artifact).where(
            Artifact.research_id == r.id, Artifact.kind == "k8s-experiment"
        ).order_by(Artifact.id.desc()).limit(1)
    )).scalar_one_or_none()
    if exp is not None:
        try:
            import json as _json
            d = _json.loads(exp.content)
            k8s_summary = (
                f"实测: {d.get('passed', 0)}/{d.get('actual_total', d.get('total', 0))} "
                f"断言通过" + (f"（{d.get('skipped', 0)} 跳过）" if d.get('skipped') else "")
            )
        except Exception:
            k8s_summary = ""

    return {
        "id": r.id,
        "iteration": r.iteration,
        "title": r.title,
        "goal": r.goal,
        "constraints": r.constraints,
        "expected_output": r.expected_output,
        "depth": r.depth,
        "priority": r.priority,
        "status": r.status,
        "score": score,
        "report_excerpt": report_excerpt,
        "k8s_summary": k8s_summary,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


async def _load_topic_sessions(session: AsyncSession, topic_id: str) -> list[Research]:
    return (await session.execute(
        select(Research)
        .where(Research.topic_id == topic_id)
        .order_by(Research.iteration)
    )).scalars().all()


@router.get("")
async def list_topics(session: AsyncSession = Depends(get_session_dep)):
    topics = (await session.execute(
        select(ResearchTopic).order_by(ResearchTopic.updated_at.desc())
    )).scalars().all()
    out = []
    for t in topics:
        rs = await _load_topic_sessions(session, t.id)
        sessions = []
        for r in rs:
            sessions.append(await _research_out(session, r))
        out.append(_topic_out(t, sessions))
    return {"items": out, "total": len(out)}


@router.post("", status_code=201)
async def create_topic(body: TopicCreate, session: AsyncSession = Depends(get_session_dep)):
    t = ResearchTopic(name=body.name, description=body.description)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return {"id": t.id, "name": t.name, "description": t.description}


@router.get("/{topic_id}")
async def get_topic(topic_id: str, session: AsyncSession = Depends(get_session_dep)):
    t = (await session.execute(
        select(ResearchTopic).where(ResearchTopic.id == topic_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "topic not found")
    rs = await _load_topic_sessions(session, topic_id)
    sessions = []
    for r in rs:
        sessions.append(await _research_out(session, r))
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "sessions": sessions,
        "total": len(sessions),
        # baseline + trend (same computation as _topic_out)
        **_topic_out(t, sessions),
    }


@router.delete("/{topic_id}", status_code=204)
async def delete_topic(topic_id: str, session: AsyncSession = Depends(get_session_dep)):
    t = (await session.execute(
        select(ResearchTopic).where(ResearchTopic.id == topic_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "topic not found")
    await session.delete(t)
    await session.commit()


@router.post("/{topic_id}/iterate", status_code=201)
async def iterate_topic(
    topic_id: str,
    body: IterateRequest,
    session: AsyncSession = Depends(get_session_dep),
):
    """Launch the next iteration of a topic.

    Carries the latest round's research boundary forward, applies any
    adjustments from the request, creates a new Research (next iteration),
    and snapshots it as version 1.
    """
    t = (await session.execute(
        select(ResearchTopic).where(ResearchTopic.id == topic_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "topic not found")

    latest = (await session.execute(
        select(Research)
        .where(Research.topic_id == topic_id)
        .order_by(Research.iteration.desc())
        .limit(1)
    )).scalar_one_or_none()

    # Build the new round's boundary from the latest + overrides.
    base = latest
    title = (latest.title if latest else t.name)
    if latest is not None and not body.goal and body.commit_message:
        pass  # keep base boundary

    # First round of a fresh topic: if no goal was supplied, derive a usable
    # one from the topic name so the research is immediately executable.
    goal = body.goal if body.goal is not None else (base.goal if base else "")
    if not goal.strip():
        goal = f"对「{t.name}」进行系统性预研：梳理背景、对比主流方案、识别关键权衡，并给出可落地的推荐与实施建议。"

    new_r = Research(
        title=title,
        goal=goal,
        constraints=body.constraints if body.constraints is not None else (base.constraints if base else ""),
        expected_output=body.expected_output if body.expected_output is not None else (base.expected_output if base else ""),
        depth=body.depth or (base.depth if base else "standard"),
        priority=body.priority or (base.priority if base else "medium"),
        estimated_cost=base.estimated_cost if base else 0.0,
        requires_k8s_validation=base.requires_k8s_validation if base else 0,
        use_custom_style=base.use_custom_style if base else 0,
        style_id=base.style_id if base else None,
        topic_id=t.id,
        iteration=(latest.iteration + 1) if latest else 1,
        status="pending",
    )
    session.add(new_r)
    await session.flush()

    # Snapshot v1 for the new round.
    from app.services.history import record_version
    await record_version(
        session, new_r,
        commit_message=body.commit_message or f"迭代 {new_r.iteration} 启动",
        created_by="user",
    )
    await session.commit()
    await session.refresh(new_r)
    return await _research_out(session, new_r)
