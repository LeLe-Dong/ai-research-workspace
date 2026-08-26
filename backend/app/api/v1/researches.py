from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session_dep
from app.db.models import Research
from app.schemas.research import (
    ResearchCreate, ResearchDetail, ResearchSummary, ResearchProgress,
    ReviewSummary,
)
from app.services.research import (
    create_research, list_researches, get_research_with_review, delete_research,
)

router = APIRouter(prefix="/researches", tags=["researches"])


class GeneratePlanRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=500, description="One-line research subject")
    use_llm: bool = True


@router.post("/generate-plan")
async def generate_plan(body: GeneratePlanRequest):
    """Generate a complete research plan from a one-line subject.

    The user only types "评估 Redis 集群高可用方案"; we return a full,
    ready-to-submit spec (title/goal/constraints/expected_output/depth/
    priority/requires_k8s_validation) that the UI can preview + confirm.
    Uses the local hermes CLI (no dependence on the exhausted Stepfun quota),
    with an offline heuristic fallback.
    """
    from app.services.plan_generator import generate_plan as _gen
    plan = await _gen(body.subject, use_llm=body.use_llm)
    return {"subject": body.subject, "plan": plan, "source": "hermes-or-fallback"}


@router.post("", response_model=ResearchDetail, status_code=status.HTTP_201_CREATED)
async def create(payload: ResearchCreate, session: AsyncSession = Depends(get_session_dep)):
    r = await create_research(session, payload)
    return ResearchDetail.model_validate(r)


@router.get("", response_model=list[ResearchSummary])
async def list_all(
    session: AsyncSession = Depends(get_session_dep),
    limit: int = 50,
    tag: str | None = None,  # Filter by tag name
    q: str | None = None,    # Search in title/goal
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
        tag_obj = (await session.execute(
            select(Tag).where(Tag.name == tag.strip().lower())
        )).scalar_one_or_none()
        if tag_obj:
            query = query.join(ResearchTag, Research.id == ResearchTag.research_id).where(
                ResearchTag.tag_id == tag_obj.id
            )
        else:
            return []

    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            (Research.title.ilike(pattern)) | (Research.goal.ilike(pattern))
        )

    rows = (await session.execute(query)).scalars().unique().all()

    # Batch-fetch scores for all researches in one query
    research_ids = [r.id for r in rows]
    scores_map: dict[str, float] = {}
    if research_ids:
        from app.db.models import Review
        rv_rows = (await session.execute(
            select(Review.research_id, Review.overall_score)
            .where(Review.research_id.in_(research_ids))
        )).all()
        scores_map = {rid: sc for rid, sc in rv_rows}

    return [
        ResearchSummary(
            id=r.id, title=r.title, status=r.status, priority=r.priority, depth=r.depth,
            score=round(scores_map.get(r.id, 0.0), 1) if r.status == "completed" else None,
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


@router.get("/{research_id}/summary", response_model=ResearchProgress)
async def get_progress_summary(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    """One round-trip aggregated view of a research's execution state.

    Replaces the previous 7-call pattern (researches + tasks + timeline +
    artifacts + report + review + versions). Surfaces coverage gaps explicitly
    so failed / crashed researches make their incompleteness visible.
    """
    from sqlalchemy import func, select
    from app.db.models import (
        Research, Task, TimelineEvent, Artifact, Review, ResearchVersion,
    )
    from app.schemas.research import ResearchProgress, ReviewSummary

    # 1. Research row
    r = (await session.execute(
        select(Research).where(Research.id == research_id)
    )).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Research not found")

    # 2. Tasks counts
    tasks_rows = (await session.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.research_id == research_id)
        .group_by(Task.status)
    )).all()
    total_tasks = sum(c for _, c in tasks_rows)
    done_tasks = sum(c for s, c in tasks_rows if s == "done")

    # 3. Timeline aggregates
    tl_agg = (await session.execute(
        select(
            func.count(TimelineEvent.id),
            func.min(TimelineEvent.ts),
            func.max(TimelineEvent.ts),
        ).where(TimelineEvent.research_id == research_id)
    )).one()
    tl_count = tl_agg[0]
    tl_first, tl_last = tl_agg[1], tl_agg[2]
    tl_gap_sec = (tl_last - tl_first).total_seconds() if (tl_first and tl_last) else None

    # 4. Artifacts
    art_rows = (await session.execute(
        select(Artifact.kind, Artifact.title, Artifact.version,
               func.length(Artifact.content))
        .where(Artifact.research_id == research_id)
        .order_by(Artifact.created_at)
    )).all()
    artifacts = [
        {"kind": k, "title": t, "version": v, "size_bytes": sz}
        for k, t, v, sz in art_rows
    ]

    # 5. Versions (just count + latest report length)
    versions_count = (await session.execute(
        select(func.count(ResearchVersion.id))
        .where(ResearchVersion.research_id == research_id)
    )).scalar() or 0
    latest_report_len = (await session.execute(
        select(func.length(ResearchVersion.report_markdown))
        .where(ResearchVersion.research_id == research_id)
        .order_by(ResearchVersion.version.desc())
        .limit(1)
    )).scalar() or 0

    # 6. Review
    rv = (await session.execute(
        select(Review).where(Review.research_id == research_id)
    )).scalar_one_or_none()
    review_model = None
    score_val = None
    if rv is not None:
        score_val = rv.overall_score
        review_model = ReviewSummary(
            overall_score=rv.overall_score,
            dimensions=rv.dimensions,
            strengths=rv.strengths,
            weaknesses=rv.weaknesses,
            suggestions=rv.suggestions,
            threshold=rv.threshold,
        )

    # 8. Duration (compute first so coverage_gaps can use it)
    duration_sec = (r.updated_at - r.created_at).total_seconds() if r.updated_at and r.created_at else None

    # 7. Coverage gaps (the bit that makes this endpoint useful for debugging
    # failed / crashed researches — surfaces what's missing explicitly)
    gaps: list[str] = []
    if total_tasks == 0:
        gaps.append("tasks 表为空：研究从未真正启动或第一段就崩了")
    if tl_count <= 5:
        gaps.append(f"timeline 只剩 {tl_count} 条事件，可能在 phase 1/2 卡死")
    if tl_first and tl_last and (tl_last - tl_first).total_seconds() < 60 and r.status != "completed":
        gaps.append("timeline 跨度 < 60 秒但未完成，可能在第一次 LLM 调之前就 crash")
    if duration_sec is not None and tl_gap_sec is not None:
        # The strongest signal of a stuck-killed research: duration is huge
        # (recorded wall clock) but timeline only covers the first few seconds.
        # If the timeline only covers <2min but the row sat for >5min, the
        # asyncio task died early and the watchdog finally updated its status.
        if r.status != "completed" and duration_sec > 300 and tl_gap_sec < 120:
            gaps.append(
                f"duration={duration_sec:.0f}s vs timeline_gap={tl_gap_sec:.1f}s — "
                f"任务在最初 {tl_gap_sec:.0f}s 内写入 {tl_count} 条事件后就停了，"
                f"后续 {duration_sec - tl_gap_sec:.0f}s 没有新事件（asyncio task 已死）"
            )
    if r.status == "failed" and not r.error_message:
        gaps.append("status=failed 但 error_message 为空，watchdog 没写诊断")
    if r.status == "completed" and score_val is None:
        gaps.append("completed 但无 review，评审 phase 异常退出")
    if not artifacts and r.status == "completed":
        gaps.append("completed 但没有 artifacts（report/mermaid/comparison 缺失）")
    if latest_report_len < 500 and r.status == "completed":
        gaps.append(f"report 长度仅 {latest_report_len} 字符，可能 truncation")

    return ResearchProgress(
        id=r.id, title=r.title, status=r.status, priority=r.priority, depth=r.depth,
        error_message=r.error_message,
        created_at=r.created_at, updated_at=r.updated_at,
        duration_sec=duration_sec,
        progress_tasks_done=done_tasks,
        progress_tasks_total=total_tasks,
        progress_tasks_pct=(done_tasks / total_tasks * 100) if total_tasks else 0.0,
        progress_timeline_events=tl_count,
        progress_timeline_first=tl_first,
        progress_timeline_last=tl_last,
        progress_timeline_gap_sec=tl_gap_sec,
        score=score_val,
        review=review_model,
        artifacts=artifacts,
        report_length_chars=latest_report_len,
        versions_count=versions_count,
        coverage_gaps=gaps,
    )


@router.delete("/{research_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    ok = await delete_research(session, research_id)
    if not ok:
        raise HTTPException(404, "Research not found")
    return None
