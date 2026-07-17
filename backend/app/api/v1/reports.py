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
    raw_md = by_kind.get("markdown").content if by_kind.get("markdown") else None
    clean_md = _get_clean_content(raw_md)

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
            "executive_summary": _extract_executive_summary(clean_md) if clean_md else None,
            "research_flow_diagram": by_kind.get("mermaid").content if by_kind.get("mermaid") else None,
            "comparison_table": by_kind.get("table").content if by_kind.get("table") else None,
        },
        "full_report": clean_md,
        "is_truncated": _is_truncated(raw_md),
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




def _is_truncated(content):
    """Detect if report was truncated by max_tokens during generation."""
    if not content:
        return False
    return "[truncated" in content or "[truncated: max_tokens reached]" in content


def _get_clean_content(content):
    """Strip the [truncated: max_tokens reached] marker from a report."""
    if not content:
        return ""
    import re as _re
    return _re.sub(r"\s*\[truncated[^\]]*\]\s*", "\n", content).strip()


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



@router.post("/{research_id}/regenerate-report")
async def regenerate_report(
    research_id: str,
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    """Re-run only the report phase for a completed research.

    Useful when the original report was truncated by max_tokens. Bumps the
    version on the new artifact, replaces the old markdown/mermaid/table artifacts.
    Returns the new full_report markdown.
    """
    from app.agents.stepfun import StepfunAgentClient
    from app.core.config import settings
    from app.agents.prompts import (
        UNDERSTAND_SYSTEM, UNDERSTAND_USER_TEMPLATE,
        ANALYZE_SYSTEM, ANALYZE_USER_TEMPLATE,
        REPORT_SYSTEM, REPORT_USER_TEMPLATE,
    )
    from app.db.models import Research as _R, Artifact as _A

    if not settings.stepfun_api_key:
        raise HTTPException(503, "stepfun API key not configured")

    r = (await session.execute(
        select(_R).where(_R.id == research_id)
    )).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Research not found")

    # Get existing artifacts to find findings + analysis
    arts = (await session.execute(
        select(_A).where(_A.research_id == research_id).order_by(_A.created_at)
    )).scalars().all()
    by_kind = {a.kind: a for a in arts}
    findings = by_kind.get("findings")
    analysis = by_kind.get("analysis")

    # For older researches without findings/analysis artifacts, fall back to the existing markdown
    if not findings:
        existing_md = by_kind.get("markdown")
        if existing_md and existing_md.content:
            findings = existing_md  # use existing markdown as base
        else:
            raise HTTPException(400, "No findings or markdown artifact to base report on")

    client = StepfunAgentClient(
        api_key=settings.stepfun_api_key,
        model=settings.stepfun_model,
        base_url=settings.stepfun_base_url,
    )

    # Re-run only the report phase
    report_md = ""
    try:
        report_md = await client.llm.chat(
            REPORT_SYSTEM,
            REPORT_USER_TEMPLATE.format(
                title=r.title, goal=r.goal,
                constraints=r.constraints or "(none)",
                expected_output=r.expected_output or "(none)",
                depth=r.depth or "standard",
                findings=findings.content[:4000],
                analysis=(analysis.content[:2000] if analysis else ""),
                images="(skip — re-running with limited context)",
            ),
            max_tokens=16000,
        )
    except Exception as e:
        raise HTTPException(502, f"Regenerate failed: {e}")

    from app.agents.stepfun import _rewrite_image_urls_to_proxy
    import json as _json
    report_md = _rewrite_image_urls_to_proxy(report_md.strip())

    # Bump version on existing markdown artifact, replace content
    md_art = by_kind.get("markdown")
    if md_art is not None:
        md_art.content = report_md
        md_art.version += 1
        session.add(md_art)
    else:
        session.add(_A(
            research_id=research_id,
            kind="markdown",
            title="Final Report",
            content=report_md,
            version=1,
        ))

    await session.commit()

    return {
        "ok": True,
        "research_id": research_id,
        "version": (md_art.version if md_art else 1),
        "chars": len(report_md),
        "full_report": report_md,
    }
