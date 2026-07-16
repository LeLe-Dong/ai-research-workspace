"""Admin API: runtime configuration overrides.

Endpoints:
  GET  /api/v1/admin/agent-mode       — get current mode (DB override or env default)
  POST /api/v1/admin/agent-mode       — change mode (writes to DB + spawns restart watcher)
  GET  /api/v1/admin/restart-status   — last restart attempt result
"""
import asyncio
import logging
import os
import signal
import subprocess
import time
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
    mode: Literal["mock", "stepfun", "hermes-researcher"]
    stepfun_api_key: str | None = None  # optional override


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
    """Persist new agent mode to DB. Caller must restart the backend for change to take effect.

    If AIRW_AUTO_RESTART=1, this endpoint will also spawn a restart watcher that
    kills the current uvicorn and starts a new one with the new mode (via setsid).
    """
    new_mode = payload.mode

    # Persist to DB
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

    # Spawn restart watcher
    auto_restart = os.environ.get("AIRW_AUTO_RESTART", "1") == "1"
    if auto_restart:
        _spawn_restart_watcher(new_mode)
        return {
            "status": "restarting",
            "mode": new_mode,
            "message": "已切换模式。系统将在 3 秒内重启后端服务（约 5-10 秒不可用）。",
        }
    return {
        "status": "updated_db",
        "mode": new_mode,
        "message": "已写入数据库。请手动重启后端服务生效。",
    }


def _spawn_restart_watcher(new_mode: str) -> None:
    """Spawn an independent process (setsid) that kills the current uvicorn
    and starts a new one with the new agent mode. The watcher itself stays alive
    independently of the current uvicorn process (via setsid + nohup)."""
    import tempfile

    backend_dir = "/root/workspace/ai-research-workspace/backend"
    venv_activate = "source /root/workspace/ai-test-platform/.venv/bin/activate"

    # Build env vars to pass through to the new uvicorn
    env_exports = [
        f"export AIRW_AGENT_MODE={new_mode}",
    ]
    # Preserve stepfun API key
    if os.environ.get("AIRW_STEPFUN_API_KEY"):
        env_exports.append(
            f"export AIRW_STEPFUN_API_KEY='{os.environ['AIRW_STEPFUN_API_KEY']}'"
        )
    if os.environ.get("AIRW_STEPFUN_MODEL"):
        env_exports.append(
            f"export AIRW_STEPFUN_MODEL={os.environ['AIRW_STEPFUN_MODEL']}"
        )
    env_exports.append("export AIRW_DB_PATH=storage/airw.db")

    # Marker: write to DB to confirm restart happened
    marker = f"export AIRW_RESTART_MARKER={int(time.time())}"

    script = f"""#!/bin/bash
# Auto-generated restart watcher for AIRW backend
# Kills current uvicorn and starts a new one with new mode.

set -e
LOG=/tmp/airw-restart.log
echo "[$(date)] Restart watcher started (new mode={new_mode})" >> $LOG

# Wait briefly so the HTTP response can complete
sleep 3

# Find and kill the current uvicorn for port 8003
echo "[$(date)] Killing current uvicorn..." >> $LOG
for pid in $(ss -tlnp 2>/dev/null | grep ':8003 ' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u); do
    echo "[$(date)] Killing pid=$pid" >> $LOG
    kill -TERM $pid 2>/dev/null || true
done
# Also kill any python uvicorn matching our backend
pkill -TERM -f 'app.main:app.*--port 8003' 2>/dev/null || true

# Wait for processes to exit
sleep 2

# Start new uvicorn
cd {backend_dir}
{chr(10).join(env_exports)}
{marker}

nohup python -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8003 \
    --log-level warning \
    > /tmp/airw-uvicorn.log 2>&1 &

NEW_PID=$!
echo "[$(date)] New uvicorn started pid=$NEW_PID" >> $LOG
disown
exit 0
"""

    fd, path = tempfile.mkstemp(suffix=".sh", prefix="airw-restart-")
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, 0o755)

    # Spawn detached (setsid makes it independent of current process group)
    subprocess.Popen(
        [path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # equivalent to setsid
        env={**os.environ, "AIRW_RESTART_SCRIPT": path},
    )
    logger.info(f"Restart watcher spawned: {path}")


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
