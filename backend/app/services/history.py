"""History service: version snapshots, diff, fork."""
import json
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Research, ResearchVersion


async def get_versions(session: AsyncSession, research_id: str) -> list[dict]:
    """List all versions for a research."""
    result = await session.execute(
        select(ResearchVersion)
        .where(ResearchVersion.research_id == research_id)
        .order_by(ResearchVersion.version.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "id": v.id,
            "version": v.version,
            "title": v.title,
            "status": v.status,
            "created_at": v.created_at.isoformat(),
            "created_by": v.created_by,
            "commit_message": v.commit_message,
            "parent_version": v.parent_version,
        }
        for v in versions
    ]


async def get_version_detail(session: AsyncSession, research_id: str, version: int) -> dict | None:
    """Get a single version snapshot."""
    result = await session.execute(
        select(ResearchVersion).where(
            ResearchVersion.research_id == research_id,
            ResearchVersion.version == version,
        )
    )
    v = result.scalar_one_or_none()
    if not v:
        return None
    return {
        "id": v.id,
        "version": v.version,
        "title": v.title,
        "goal": v.goal,
        "constraints": v.constraints,
        "expected_output": v.expected_output,
        "depth": v.depth,
        "priority": v.priority,
        "estimated_cost": v.estimated_cost,
        "status": v.status,
        "report_markdown": v.report_markdown,
        "review_json": v.review_json,
        "created_at": v.created_at.isoformat(),
        "created_by": v.created_by,
        "commit_message": v.commit_message,
        "parent_version": v.parent_version,
    }


async def diff_versions(session: AsyncSession, research_id: str, v1: int, v2: int) -> dict:
    """Diff two versions: fields + report."""
    r1 = await get_version_detail(session, research_id, v1)
    r2 = await get_version_detail(session, research_id, v2)
    if not r1 or not r2:
        raise ValueError("version not found")

    fields = ["title", "goal", "constraints", "expected_output", "depth", "priority", "estimated_cost", "status"]
    field_diffs = []
    for f in fields:
        a, b = r1.get(f, ""), r2.get(f, "")
        if a != b:
            field_diffs.append({"field": f, "v1": a, "v2": b})

    report_diffs = []
    if r1.get("report_markdown") != r2.get("report_markdown"):
        report_diffs.append({
            "field": "report_markdown",
            "changed": True,
            "v1_len": len(r1.get("report_markdown") or ""),
            "v2_len": len(r2.get("report_markdown") or ""),
        })

    return {
        "research_id": research_id,
        "v1": v1,
        "v2": v2,
        "field_diffs": field_diffs,
        "report_diffs": report_diffs,
        "changed": len(field_diffs) + len(report_diffs) > 0,
    }


async def fork_version(session: AsyncSession, research_id: str, version: int, commit_message: str | None = None) -> Research:
    """Create a new research from a historical version snapshot."""
    v = await get_version_detail(session, research_id, version)
    if not v:
        raise ValueError("version not found")

    # Get next version number for the new research (will be version 1 of new research)
    new_id = __import__("uuid").uuid4().hex[:12]
    new_research = Research(
        id=new_id,
        title=f"{v['title']} (fork v{version})",
        goal=v["goal"],
        constraints=v["constraints"],
        expected_output=v["expected_output"],
        depth=v["depth"],
        priority=v["priority"],
        estimated_cost=v["estimated_cost"],
        status="pending",
    )
    session.add(new_research)
    await session.flush()

    # Create version 1 snapshot for the new research
    v1 = ResearchVersion(
        research_id=new_id,
        version=1,
        title=new_research.title,
        goal=new_research.goal,
        constraints=new_research.constraints,
        expected_output=new_research.expected_output,
        depth=new_research.depth,
        priority=new_research.priority,
        estimated_cost=new_research.estimated_cost,
        status="pending",
        created_by="fork",
        commit_message=commit_message or f"Forked from {research_id} v{version}",
        parent_version=None,
    )
    session.add(v1)
    await session.commit()
    await session.refresh(new_research)
    return new_research


async def record_version(session: AsyncSession, research: Research, commit_message: str | None = None, created_by: str = "user") -> ResearchVersion:
    """Record a version snapshot after a research is created or rerun."""
    # Extract fields before any DB ops to avoid lazy-load after commit
    research_id = research.id
    title = research.title
    goal = research.goal
    constraints = research.constraints
    expected_output = research.expected_output
    depth = research.depth
    priority = research.priority
    estimated_cost = research.estimated_cost
    status = research.status

    # Get next version number
    result = await session.execute(
        select(func.max(ResearchVersion.version)).where(ResearchVersion.research_id == research_id)
    )
    max_v = result.scalar_one_or_none() or 0
    next_v = max_v + 1
    parent_v = max_v if max_v > 0 else None

    # Get report + review artifacts if available
    report_md = None
    review_json = None
    if status in ("completed", "failed"):
        from app.db.models import Artifact
        art_result = await session.execute(
            select(Artifact).where(
                Artifact.research_id == research.id,
                Artifact.kind == "markdown",
            ).order_by(Artifact.created_at.desc())
        )
        art = art_result.scalars().first()
        if art:
            report_md = art.content

    version = ResearchVersion(
        research_id=research.id,
        version=next_v,
        title=research.title,
        goal=research.goal,
        constraints=research.constraints,
        expected_output=research.expected_output,
        depth=research.depth,
        priority=research.priority,
        estimated_cost=research.estimated_cost,
        status=research.status,
        report_markdown=report_md,
        review_json=review_json,
        created_by=created_by,
        commit_message=commit_message or ("初始版本" if next_v == 1 else f"版本 {next_v}"),
        parent_version=parent_v,
    )
    session.add(version)
    await session.flush()
    return version

