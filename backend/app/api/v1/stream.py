"""Server-Sent Events stream of timeline + artifact + status updates for one research.

Wire format (each line a JSON-encoded envelope):
  data: {"type": "timeline", "event": {...}}
  data: {"type": "task", "task": {...}}
  data: {"type": "artifact", "artifact": {...}}
  data: {"type": "status", "status": "running|completed|failed"}
  data: {"type": "heartbeat", "ts": "..."}
  data: {"type": "end", "reason": "..."}

Client connects once; receives catch-up from since=0, then live updates.

Hybrid delivery:
- Primary: in-memory event_bus (per-research asyncio.Queue) the executor
  publishes to the moment it commits a row. This gives true real-time feel
  (sub-second latency) and survives burst writes.
- Secondary: DB poll every 250ms as a safety net for events missed during
  long-running transactions, lost task-bus envelopes, or late SSE clients
  that connect after the executor has finished.
"""
import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.db.database import get_session
from app.db.models import Artifact, Research, Task, TimelineEvent
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/researches", tags=["stream"])


async def _fetch_state(research_id: str, since_seq: int) -> dict:
    """Snapshot research state since sequence."""
    async with get_session() as session:
        r = (await session.execute(
            select(Research).where(Research.id == research_id)
        )).scalar_one_or_none()
        if r is None:
            return {"error": "not_found"}

        events = (await session.execute(
            select(TimelineEvent)
            .where(TimelineEvent.research_id == research_id, TimelineEvent.sequence > since_seq)
            .order_by(TimelineEvent.sequence)
        )).scalars().all()

        artifacts = (await session.execute(
            select(Artifact)
            .where(Artifact.research_id == research_id)
            .order_by(Artifact.created_at)
        )).scalars().all()

        tasks = (await session.execute(
            select(Task).where(Task.research_id == research_id).order_by(Task.order_index)
        )).scalars().all()

        return {
            "status": r.status,
            "events": [
                {
                    "id": e.id, "ts": e.ts.isoformat(), "phase": e.phase,
                    "level": e.level, "title": e.title, "detail": e.detail,
                    "sequence": e.sequence,
                } for e in events
            ],
            "artifacts": [
                {
                    "id": a.id, "kind": a.kind, "title": a.title,
                    "content": a.content, "version": a.version,
                    "created_at": a.created_at.isoformat(),
                } for a in artifacts
            ],
            "tasks": [
                {
                    "id": t.id, "parent_id": t.parent_id, "name": t.name,
                    "phase": t.phase, "status": t.status, "progress": t.progress,
                    "order_index": t.order_index,
                } for t in tasks
            ],
        }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/{research_id}/stream")
async def stream(research_id: str, since: int = Query(default=0, ge=0)):
    """SSE stream. Wait for agent materialization, emit catch-up, then live updates.

    Real-time path: executor publishes to `event_bus` per commit → SSE picks
    up the queue immediately. DB poll at 250ms is a safety net for anything
    missed (transaction boundaries, lost wakeups, late clients).
    """
    last_seq = since
    last_status = None
    last_artifact_ids: set[str] = set()
    last_task_dump: str = ""

    async def gen():
        nonlocal last_seq, last_status, last_artifact_ids, last_task_dump
        try:
            # Wait briefly for the agent job to materialize rows (max 5s).
            for _ in range(20):
                snap = await _fetch_state(research_id, since)
                if "error" in snap:
                    yield _sse({"type": "error", "message": snap["error"]})
                    return
                if snap.get("status") != "pending" or snap.get("events") or snap.get("tasks"):
                    break
                await asyncio.sleep(0.25)

            snap = await _fetch_state(research_id, since)
            if "error" in snap:
                yield _sse({"type": "error", "message": snap["error"]})
                return

            last_status = snap["status"]
            for evt in snap["events"]:
                yield _sse({"type": "timeline", "event": evt})
                last_seq = max(last_seq, evt["sequence"])
            for art in snap["artifacts"]:
                yield _sse({"type": "artifact", "artifact": art})
                last_artifact_ids.add(art["id"])
            for t in snap["tasks"]:
                yield _sse({"type": "task", "task": t})
            last_task_dump = json.dumps(snap["tasks"], sort_keys=True)
            yield _sse({"type": "status", "status": snap["status"]})

            start = asyncio.get_event_loop().time()
            max_duration = 300.0

            # Hybrid loop: drain event_bus quickly (≤200ms per item via
            # wait_for) but periodically (every 250ms) poll DB to catch
            # anything the bus missed.
            bus_iter = event_bus.subscribe(research_id).__aiter__()
            while True:
                if asyncio.get_event_loop().time() - start > max_duration:
                    yield _sse({"type": "end", "reason": "max_duration"})
                    return

                # 1) Drain one bus item (with 250ms budget so we don't block
                # the DB poll indefinitely on a quiet executor).
                bus_pushed = False
                try:
                    kind, payload = await asyncio.wait_for(
                        bus_iter.__anext__(), timeout=0.25
                    )
                    if kind == "__end__":
                        yield _sse({"type": "end", "reason": payload.get("reason", "closed")})
                        return
                    if kind == "__heartbeat__":
                        # Don't emit a frontend heartbeat; just loop.
                        bus_pushed = False
                    elif kind == "timeline":
                        yield _sse({"type": "timeline", "event": payload})
                        last_seq = max(last_seq, payload.get("sequence", 0))
                        bus_pushed = True
                    elif kind == "artifact":
                        yield _sse({"type": "artifact", "artifact": payload})
                        last_artifact_ids.add(payload.get("id", ""))
                        bus_pushed = True
                except asyncio.TimeoutError:
                    # No bus events this tick; fall through to DB poll.
                    pass
                except StopAsyncIteration:
                    pass

                # 2) Safety-net DB poll (always, even after bus event, to
                # catch anything the executor published before SSE connected).
                snap = await _fetch_state(research_id, last_seq)
                if "error" in snap:
                    return

                for evt in snap["events"]:
                    yield _sse({"type": "timeline", "event": evt})
                    last_seq = max(last_seq, evt["sequence"])

                for art in snap["artifacts"]:
                    if art["id"] not in last_artifact_ids:
                        yield _sse({"type": "artifact", "artifact": art})
                        last_artifact_ids.add(art["id"])

                task_dump = json.dumps(snap["tasks"], sort_keys=True)
                if task_dump != last_task_dump:
                    for t in snap["tasks"]:
                        yield _sse({"type": "task", "task": t})
                    last_task_dump = task_dump

                if snap["status"] != last_status:
                    last_status = snap["status"]
                    yield _sse({"type": "status", "status": snap["status"]})

                if snap["status"] in ("completed", "failed"):
                    yield _sse({"type": "end", "reason": "completed"})
                    return

                # Heartbeat every ~1s to keep the connection alive.
                if not bus_pushed:
                    yield _sse({"type": "heartbeat", "ts": datetime.utcnow().isoformat()})
                    await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("SSE stream error")
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
