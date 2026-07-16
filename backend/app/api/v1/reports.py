"""Report assembly: combines artifacts + review into a structured report."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session_dep
from app.db.models import Artifact, Research, Review

router = APIRouter(prefix="/researches", tags=["reports"])


def _extract_executive_summary(md: str) -> str:
    """Extract Executive Summary section from a markdown report. Falls back to first 1500 chars."""
    import re as _re
    if not md:
        return ""
    m = _re.search(
        r"(?ims)^##\s+(?:1\.\s*Executive Summary|Executive Summary)\s*\n(.*?)(?=^##\s+|\Z)",
        md,
    )
    if m:
        return f"## 1. Executive Summary\n\n{m.group(1).strip()}"
    return md[:1500]


@router.get("/{research_id}/report")
async def report(research_id: str, session: AsyncSession = Depends(get_session_dep)):
    r = (await session.execute(
        select(Research).where(Research.id == research_id)
    )).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Research not found")

    artifacts = (await session.execute(
        select(Artifact).where(Artifact.research_id == research_id).order_by(Artifact.created_at)
    )).scalars().all()

    review = (await session.execute(
        select(Review).where(Review.research_id == research_id)
    )).scalar_one_or_none()

    by_kind = {a.kind: a for a in artifacts}
    full_md = by_kind.get("markdown").content if by_kind.get("markdown") else None

    return {
        "research": {
            "id": r.id, "title": r.title, "goal": r.goal,
            "constraints": r.constraints, "expected_output": r.expected_output,
            "depth": r.depth, "priority": r.priority,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        },
        "sections": {
            "executive_summary": _extract_executive_summary(full_md) if full_md else None,
            "research_flow_diagram": by_kind.get("mermaid").content if by_kind.get("mermaid") else None,
            "comparison_table": by_kind.get("table").content if by_kind.get("table") else None,
        },
        "full_report": full_md,
        "review": _build_review_payload(review) if review else None,
    }


def _parse_json_list(s: str | None) -> list:
    """Parse a JSON-encoded list field. Returns [] on error or empty input."""
    if not s:
        return []
    import json as _json
    try:
        v = _json.loads(s)
        return v if isinstance(v, list) else [v]
    except Exception:
        # Legacy: split on common delimiters
        if isinstance(s, str) and s:
            parts = [p.strip() for p in s.replace("\n\n", "\n").split("\n") if p.strip()]
            return parts if parts else [s]
        return []


def _build_review_payload(review) -> dict:
    """Build the review payload, preferring structured lists over legacy strings."""
    return {
        "overall_score": review.overall_score,
        "dimensions": review.dimensions or {},
        "verdict": review.verdict or "",
        # Prefer new *_list fields, fall back to legacy strings
        "strengths": _parse_json_list(review.strengths_list) or _parse_json_list(review.strengths),
        "weaknesses": _parse_json_list(review.weaknesses_list) or _parse_json_list(review.weaknesses),
        "improvements": _parse_json_list(review.improvements),
        "critical_questions": _parse_json_list(review.critical_questions),
        "next_steps": _parse_json_list(review.next_steps),
        "suggestions": review.suggestions or "",
        "threshold": review.threshold,
    }


async def list_completed(session: AsyncSession = Depends(get_session_dep), limit: int = 50):
    """All completed researches (registered at /api/v1/completed-researches)."""
    from app.core.cache import TTLCache
    completed_cache = TTLCache(default_ttl=10.0)

    async def _compute():
        from sqlalchemy.orm import selectinload
        # Use selectinload to eager-load reviews in a single batch query
        rows = (await session.execute(
            select(Research)
            .where(Research.status == "completed")
            .options(selectinload(Research.reviews))
            .order_by(Research.updated_at.desc())
            .limit(limit)
        )).scalars().all()

        out = []
        for r in rows:
            # Pick the latest review (or first if available)
            review = r.reviews[0] if r.reviews else None
            out.append({
                "id": r.id,
                "title": r.title,
                "goal": r.goal,
                "depth": r.depth,
                "priority": r.priority,
                "score": review.overall_score if review else None,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            })
        return out

    return await completed_cache.get_or_set(f"completed_{limit}", _compute, ttl=10.0)
