"""Orchestrate one research run: consume agent events, persist to DB.

Spawned as an asyncio task after POST /researches/{id}/start.
"""
import logging
import sys
import asyncio
import traceback
from datetime import datetime

from sqlalchemy import select

from app.agents import get_agent_client
from app.agents.base import ResearchRequest
from app.db.database import get_session
from app.db.models import Artifact, Research, Review, Task, TimelineEvent

logger = logging.getLogger(__name__)


async def _create_task_tree(session, research_id: str) -> list[Task]:
    """Create one Task row per MockAgentClient TASK_TREE entry."""
    from app.agents.mock import TASK_TREE
    tasks: list[Task] = []
    for idx, (phase, name, _desc) in enumerate(TASK_TREE):
        t = Task(
            research_id=research_id,
            parent_id=None,
            name=name,
            phase=phase,
            status="pending",
            progress=0,
            order_index=idx,
        )
        session.add(t)
        tasks.append(t)
    await session.flush()
    return tasks


async def run_research_job(research_id: str, timeout_sec: int = 900) -> None:
    """Background coroutine. Consumes agent events and persists state.

    Args:
        research_id: research to execute
        timeout_sec: max execution time before forced failure (default 15 min)
    """
    print(f"[executor] starting job for {research_id}", file=sys.stderr, flush=True)
    try:
        # Initial setup session
        async with get_session() as session:
            research = (await session.execute(
                select(Research).where(Research.id == research_id)
            )).scalar_one_or_none()
            if research is None:
                print(f"[executor] Research {research_id} not found", file=sys.stderr, flush=True)
                return

            # Idempotency: skip if already completed
            if research.status == "completed":
                print(f"[executor] {research_id} already completed, skipping", file=sys.stderr, flush=True)
                return

            # Clear old tasks and timeline to avoid FK collisions and stale state
            from sqlalchemy import delete
            from app.db.models import Task, TimelineEvent
            await session.execute(delete(Task).where(Task.research_id == research_id))
            await session.execute(delete(TimelineEvent).where(TimelineEvent.research_id == research_id))
            # Don't delete artifacts - keep history for diff

            research.status = "running"
            await session.commit()
            print(f"[executor] status -> running", file=sys.stderr, flush=True)

            tasks = await _create_task_tree(session, research_id)
            task_by_idx = {t.order_index: t for t in tasks}
            await session.commit()
            print(f"[executor] created {len(tasks)} tasks", file=sys.stderr, flush=True)

            req = ResearchRequest(
                research_id=research.id,
                title=research.title,
                goal=research.goal,
                constraints=research.constraints,
                expected_output=research.expected_output,
                depth=research.depth,
                priority=research.priority,
            )

            client = get_agent_client()
            event_count = 0

            # Bound execution with timeout
            try:
                async with asyncio.timeout(timeout_sec):
                    async for evt in client.run_research(req):
                        event_count += 1
                        now = datetime.utcnow()

                        if evt.phase != "progress":
                            session.add(TimelineEvent(
                                research_id=research_id,
                                ts=now,
                                phase=evt.phase,
                                level=evt.level,
                                title=evt.title,
                                detail=evt.detail,
                                sequence=event_count,
                            ))

                        if evt.task_id:
                            try:
                                idx = int(evt.task_id.split("-")[1])
                            except (ValueError, IndexError):
                                idx = -1
                            t = task_by_idx.get(idx)
                            if t:
                                if evt.task_progress is not None:
                                    t.progress = evt.task_progress
                                if evt.task_progress == 0 and t.status == "pending":
                                    t.status = "running"
                                    t.started_at = now
                                if evt.task_progress == 100:
                                    t.status = "done"
                                    t.finished_at = now

                        if evt.artifact:
                            session.add(Artifact(
                                research_id=research_id,
                                kind=evt.artifact["kind"],
                                title=evt.artifact["title"],
                                content=evt.artifact["content"],
                                version=1,
                            ))

                        if evt.phase == "review" and evt.level == "success":
                            for t in tasks:
                                if t.status != "done":
                                    t.status = "done"
                                    t.progress = 100
                                    t.finished_at = now
                            research.status = "completed"

                            # Record version snapshot
                            from app.services.history import record_version
                            await record_version(session, research, commit_message="自动完成", created_by="system")

                            from app.agents.mock import REVIEW_DIMENSIONS
                            overall = sum(REVIEW_DIMENSIONS.values()) / len(REVIEW_DIMENSIONS)
                            existing = (await session.execute(
                                select(Review).where(Review.research_id == research_id)
                            )).scalar_one_or_none()
                            if existing is None:
                                session.add(Review(
                                    research_id=research_id,
                                    overall_score=overall,
                                    dimensions=REVIEW_DIMENSIONS,
                                    strengths="清晰的权衡分析；具体的实施阶段。",
                                    weaknesses="对组织采用风险讨论有限。",
                                    suggestions="添加利益相关方映射和 30-60-90 推广计划。",
                                    threshold=7.0,
                                ))

                        await session.commit()

            except asyncio.TimeoutError:
                print(f"[executor] TIMEOUT {research_id} after {timeout_sec}s", file=sys.stderr, flush=True)
                # Mark as failed in a fresh session to avoid stale state
                async with get_session() as err_session:
                    err_r = (await err_session.execute(
                        select(Research).where(Research.id == research_id)
                    )).scalar_one_or_none()
                    if err_r and err_r.status == "running":
                        err_r.status = "failed"
                        err_r.updated_at = datetime.utcnow()
                        await err_session.commit()
                return

            print(f"[executor] Research {research_id} done in {event_count} events",
                  file=sys.stderr, flush=True)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[executor] FAILED {research_id}: {error_msg}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        # Mark as failed to prevent stuck state, save error for UI display
        try:
            async with get_session() as err_session:
                err_r = (await err_session.execute(
                    select(Research).where(Research.id == research_id)
                )).scalar_one_or_none()
                if err_r and err_r.status == "running":
                    err_r.status = "failed"
                    err_r.error_message = error_msg[:500]  # truncate to fit
                    err_r.updated_at = datetime.utcnow()
                    await err_session.commit()
        except Exception:
            pass  # best effort
        raise
