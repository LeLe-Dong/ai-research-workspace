"""Admin API: runtime configuration overrides.

Endpoints:
  GET  /api/v1/admin/agent-mode       — get current mode (DB override or env default)
  POST /api/v1/admin/agent-mode       — change mode (writes to DB; restarts via systemd if enabled)
  GET  /api/v1/admin/restart-status   — last restart attempt result (admin manual restarts)
"""
import asyncio
import logging
import os
import threading
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import settings
from app.db.database import get_session
from app.db.models import AppConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


class AgentModePayload(BaseModel):
    mode: Literal["mock", "llm", "hermes-researcher"]  # llm = uses LLM card config
    # Legacy field kept for backwards-compat POSTs; no longer used (LLM key lives in /config/llm)
    stepfun_api_key: str | None = None


@router.get("/agent-mode")
async def get_agent_mode() -> dict:
    """Return current effective agent mode + source (env vs db)."""
    async with get_session() as session:
        db_row = (await session.execute(
            select(AppConfig).where(AppConfig.key == "agent_mode")
        )).scalar_one_or_none()
    return {
        "mode": settings.agent_mode,
        "source": "db" if db_row else "env",
        "db_updated_at": db_row.updated_at.isoformat() if db_row else None,
        "env_default": "mock",
    }


@router.get("/restart-status")
async def get_restart_status() -> dict:
    """Check if the backend has been restarted since the last mode change."""
    async with get_session() as session:
        last = (await session.execute(
            select(AppConfig).where(AppConfig.key == "last_restart_at")
        )).scalar_one_or_none()
    return {
        "last_restart_at": last.value if last else None,
    }


@router.post("/agent-mode")
async def set_agent_mode(payload: AgentModePayload) -> dict:
    """Persist new agent mode to DB. The backend runs under systemd
    (`airw-backend.service`), and this box is configured with systemd's
    `Restart=always` so crash-recovery is automatic.

    When `AIRW_AUTO_RESTART=systemd` (default), this endpoint will additionally
    trigger a non-blocking `systemctl restart airw-backend.service` from a
    daemon thread, so the new mode is live within ~3-5 seconds without the
    user having to log in to the server. Set `AIRW_AUTO_RESTART=off` to opt out
    and require manual `sudo systemctl restart airw-backend.service`.

    Implementation note: the restart is launched via a daemon thread (NOT
    asyncio, NOT a subprocess in the request handler) because `systemctl
    restart` issues SIGTERM to the current process — we need to let this
    response escape first, then schedule the restart.
    """
    new_mode = payload.mode

    # 1) Persist to DB
    async with get_session() as session:
        existing = (await session.execute(
            select(AppConfig).where(AppConfig.key == "agent_mode")
        )).scalar_one_or_none()
        if existing:
            existing.value = new_mode
            existing.updated_at = datetime.utcnow()
        else:
            session.add(AppConfig(key="agent_mode", value=new_mode))
        if payload.stepfun_api_key:
            key_row = (await session.execute(
                select(AppConfig).where(AppConfig.key == "stepfun_api_key")
            )).scalar_one_or_none()
            if key_row:
                key_row.value = payload.stepfun_api_key
            else:
                session.add(AppConfig(key="stepfun_api_key", value=payload.stepfun_api_key))
        await session.commit()

    # 2) Decide whether to auto-restart
    auto_restart = os.environ.get("AIRW_AUTO_RESTART", "systemd").lower()
    if auto_restart == "systemd":
        # Schedule restart on a daemon thread so this response can complete first.
        # 1.2s lets the response get on the wire before SIGTERM hits us.
        def _do_restart():
            import subprocess as _sp
            try:
                _sp.run(
                    ["systemctl", "restart", "airw-backend.service"],
                    timeout=10, check=False,
                )
            except Exception as e:
                logger.error(f"systemctl restart failed: {e}")

        threading.Thread(target=_do_restart, daemon=True).start()
        return {
            "status": "restarting",
            "mode": new_mode,
            "message": (
                f"已写入数据库：mode={new_mode}。"
                "systemd 将在 1-3 秒内重启 airw-backend.service，"
                "前端会短暂连不上（约 3-5 秒），刷新即可。"
            ),
        }

    # AIRW_AUTO_RESTART=off: caller must restart manually
    return {
        "status": "updated_db",
        "mode": new_mode,
        "message": (
            f"已写入数据库：mode={new_mode}。"
            "AIRW_AUTO_RESTART=off，需要手动重启后端："
            "sudo systemctl restart airw-backend.service"
        ),
    }


# --- Stuck Research Recovery ---

class ResetStuckRequest(BaseModel):
    older_than_minutes: int = 5  # only reset running researches idle for this long
    dry_run: bool = False  # if True, only return the list without resetting


@router.get("/stuck-researches")
async def list_stuck_researches(older_than_minutes: int = 5) -> dict:
    """List researches that are stuck in 'running' state (idle > N minutes).

    A research is considered stuck if its status is 'running' but
    no timeline event was created in the last `older_than_minutes`.
    These usually indicate the executor process was killed mid-job.
    """
    from app.db.models import Research, TimelineEvent
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)

    async with get_session() as session:
        # Find all 'running' researches
        result = await session.execute(
            select(Research).where(Research.status == "running")
        )
        running = result.scalars().all()

        stuck = []
        for r in running:
            # Get latest timeline event ts
            latest_evt = (await session.execute(
                select(TimelineEvent.ts)
                .where(TimelineEvent.research_id == r.id)
                .order_by(TimelineEvent.ts.desc())
                .limit(1)
            )).scalar_one_or_none()

            last_activity = latest_evt or r.updated_at
            if last_activity < cutoff:
                stuck.append({
                    "id": r.id,
                    "title": r.title,
                    "last_activity": last_activity.isoformat(),
                    "minutes_idle": round((datetime.utcnow() - last_activity).total_seconds() / 60, 1),
                })

        return {
            "cutoff": cutoff.isoformat(),
            "older_than_minutes": older_than_minutes,
            "running_total": len(running),
            "stuck_count": len(stuck),
            "stuck": stuck,
        }


@router.post("/reset-stuck-researches")
async def reset_stuck_researches(payload: ResetStuckRequest) -> dict:
    """Reset stuck researches (status='running' but idle > N min) back to 'pending'.

    The next call to /researches/{id}/start will pick them up and rerun cleanly.
    Returns the list of reset IDs.
    """
    from app.db.models import Research, TimelineEvent
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=payload.older_than_minutes)
    reset_ids: list[str] = []

    async with get_session() as session:
        result = await session.execute(
            select(Research).where(Research.status == "running")
        )
        running = result.scalars().all()

        for r in running:
            latest_evt = (await session.execute(
                select(TimelineEvent.ts)
                .where(TimelineEvent.research_id == r.id)
                .order_by(TimelineEvent.ts.desc())
                .limit(1)
            )).scalar_one_or_none()

            last_activity = latest_evt or r.updated_at
            if last_activity < cutoff:
                if payload.dry_run:
                    # Dry run: just record what would be reset
                    reset_ids.append(r.id)
                else:
                    r.status = "pending"
                    r.updated_at = datetime.utcnow()
                    reset_ids.append(r.id)

        if not payload.dry_run and reset_ids:
            await session.commit()

    return {
        "dry_run": payload.dry_run,
        "older_than_minutes": payload.older_than_minutes,
        "reset_count": len(reset_ids),
        "reset_ids": reset_ids,
    }
