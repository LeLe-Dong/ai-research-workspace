"""Seed mock data so the dashboard looks alive even on first visit."""
from datetime import datetime, timedelta

from app.db.database import get_session
from app.db.models import Research, Task, TimelineEvent, Artifact, Review


SAMPLES = [
    {
        "title": "AI Agent Orchestration Patterns for Enterprise",
        "goal": "Compare leading agent orchestration frameworks and recommend one for enterprise adoption.",
        "priority": "high", "depth": "deep",
        "score": 9.1,
    },
    {
        "title": "PostgreSQL 17 Migration Strategy",
        "goal": "Evaluate migration paths from 15 → 17 for a 5TB production workload.",
        "priority": "high", "depth": "standard",
        "score": 8.6,
    },
    {
        "title": "Vector Database Selection for RAG",
        "goal": "Choose between pgvector, Qdrant, and Weaviate for a multi-tenant RAG system.",
        "priority": "medium", "depth": "standard",
        "score": 8.4,
    },
    {
        "title": "Frontend Architecture for AI Workspace",
        "goal": "Decide between monorepo + Next.js and Vite + multi-package split.",
        "priority": "medium", "depth": "quick",
        "score": 7.9,
    },
    {
        "title": "Observability Stack for Kubernetes",
        "goal": "Design a unified observability pipeline covering logs, metrics, traces.",
        "priority": "low", "depth": "deep",
        "score": 8.8,
    },
    {
        "title": "Real-time Collaboration CRDT Library",
        "goal": "Evaluate Yjs, Automerge, and Liveblocks for collaborative editing.",
        "priority": "low", "depth": "standard",
        "score": 7.5,
    },
]


async def seed_if_empty() -> int:
    """Insert samples only if no researches exist. Returns rows inserted."""
    async with get_session() as session:
        existing = (await session.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM researches"))).scalar()
        # Fallback path without raw SQL:
        from sqlalchemy import select, func
        cnt = (await session.execute(select(func.count(Research.id)))).scalar_one()
        if cnt > 0:
            return 0
        return await _seed(session)


async def _seed(session) -> int:
    from sqlalchemy import select, func
    inserted = 0
    now = datetime.utcnow()
    for i, sample in enumerate(SAMPLES):
        r = Research(
            title=sample["title"],
            goal=sample["goal"],
            constraints="Production-grade; on-prem deployment supported.",
            expected_output="Comparison + recommendation + implementation plan.",
            depth=sample["depth"],
            priority=sample["priority"],
            estimated_cost=12.5 + i,
            status="completed",
            created_at=now - timedelta(hours=i * 6),
            updated_at=now - timedelta(hours=i * 6),
        )
        session.add(r)
        await session.flush()

        # Add a task snapshot
        session.add(Task(
            research_id=r.id,
            name="Completed 5/5 phases",
            phase="report",
            status="done",
            progress=100,
            order_index=0,
            started_at=r.created_at,
            finished_at=r.updated_at,
        ))

        # Add a few timeline events
        for j in range(5):
            session.add(TimelineEvent(
                research_id=r.id,
                ts=r.updated_at - timedelta(minutes=10 - j),
                phase=["understand", "decompose", "search", "analyze", "summarize"][j],
                level="info",
                title=f"Step {j+1}: complete",
                detail="",
                sequence=j,
            ))

        # Add a markdown artifact
        session.add(Artifact(
            research_id=r.id,
            kind="markdown",
            title=sample["title"] + " — 最终报告",
            content=f"# {sample['title']}\n\n## 研究目标\n\n{sample['goal']}\n\n## 摘要\n\n附最终推荐方案与风险登记。",
            version=1,
        ))

        # Add a review
        session.add(Review(
            research_id=r.id,
            overall_score=sample["score"],
            dimensions={
                "technical_feasibility": sample["score"],
                "maintainability": sample["score"] - 0.5,
                "scalability": sample["score"] - 0.3,
                "risk": sample["score"] - 1.0,
                "cost": sample["score"] - 0.4,
                "innovation": sample["score"] + 0.2,
            },
            strengths="Clear trade-off analysis; concrete next steps.",
            weaknesses="Limited discussion of organizational adoption risk.",
            suggestions="Add a stakeholder map and a 30-60-90 rollout plan.",
            threshold=7.0,
        ))
        inserted += 1

    await session.commit()
    return inserted
