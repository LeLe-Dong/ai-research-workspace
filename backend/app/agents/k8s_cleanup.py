"""Resource tracking + table-driven cleanup for K8s validate phase.

Why this module exists
----------------------
Before this module, the only cleanup mechanism was a hardcoded
`kubectl delete pod airw-validate-<short>` in app.agents.k8s. That was
fine when the only resource created was the single test pod. With
ADR-002 letting the agent submit arbitrary manifests, the backend
loses the ability to know what was created — `kubectl delete -l
app=airw-validate` only catches the pod.

This module adds the tracking + cleanup-by-table path:

  1. record_resource(...)   write one row to research_resources when
                            a manifest is applied
  2. cleanup_research_resources(...)  iterate rows for a research_id,
                            kubectl delete each, mark deleted_at +
                            cleanup_status='done' once confirmed gone
  3. safety_net_cleanup   double-check the table has no pending rows
                            for this research (defensive: if the apply
                            path crashed mid-flight, rows may be in
                            'pending' with the resource still on the
                            cluster)

The full integration with validate_with_k8s is also in this module
(record on apply, run cleanup_research_resources in the finally
block). That keeps the cleanup contract in one file rather than
scattered between k8s.py and the validator.
"""
import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import select

from app.agents.k8s import _kubectl
from app.db.database import get_session
from app.db.models import ResearchResource

logger = logging.getLogger(__name__)


async def record_resource(
    *,
    research_id: str,
    kind: str,
    name: str,
    namespace: str,
    manifest_json: str = "",
    cluster_name: str | None = None,
) -> int:
    """Insert one row in research_resources. Returns the row id.

    Why a separate function: validate_with_k8s already has 5 different
    AgentEvent yields + the polling loop. Burying a SQL INSERT inside
    the same async generator makes the call site noisy. The caller
    does `await record_resource(...)` and gets back the row id.
    """
    async with get_session() as session:
        rr = ResearchResource(
            research_id=research_id,
            kind=kind,
            name=name,
            namespace=namespace,
            manifest_json=manifest_json or "",
            cluster_name=cluster_name,
            cleanup_status="pending",
        )
        session.add(rr)
        await session.commit()
        await session.refresh(rr)
        return rr.id


async def cleanup_research_resources(
    kc_path: str,
    research_id: str,
) -> dict:
    """Walk research_resources for research_id, kubectl delete each.

    Returns a dict:
      {kind, name, namespace, rc, deleted_at or None}
    per row, plus a top-level 'summary' with counts.

    Idempotency: a row that already has deleted_at set is skipped
    (returns rc=0 silently). A kubectl delete that returns NotFound
    is also treated as success.

    Sync wrapper note: _kubectl is sync (subprocess.run). We do NOT
    wrap it in asyncio — the surrounding caller is the async
    validate_with_k8s generator, which is already structured to
    tolerate blocking calls inside `async for`. We keep this function
    async to match the rest of the k8s.py surface and to make the
    caller code uniform.
    """
    results: list[dict] = []
    async with get_session() as session:
        rows = (await session.execute(
            select(ResearchResource).where(
                ResearchResource.research_id == research_id,
            ).order_by(ResearchResource.id)
        )).scalars().all()

    if not rows:
        return {"summary": "no resources tracked for this research", "items": []}

    for r in rows:
        if r.deleted_at is not None:
            results.append({
                "kind": r.kind, "name": r.name, "namespace": r.namespace,
                "rc": 0, "deleted_at": r.deleted_at.isoformat(),
                "skipped": True,
            })
            continue

        # Mark 'running' to signal we're attempting cleanup
        async with get_session() as session:
            row = (await session.execute(
                select(ResearchResource).where(
                    ResearchResource.id == r.id
                )
            )).scalars().one()
            row.cleanup_status = "running"
            await session.commit()

        # The actual delete: namespace is special-cased (delete --wait=false)
        if r.kind == "Namespace":
            rc, out, err = _kubectl(
                kc_path, "delete", "namespace", r.name,
                "--ignore-not-found=true", "--wait=false", json_out=False,
            )
        else:
            rc, out, err = _kubectl(
                kc_path, "delete", r.kind.lower(), r.name,
                "-n", r.namespace, "--ignore-not-found=true",
                "--wait=false", json_out=False,
            )

        # Idempotent: NotFound on the cluster is success
        if rc != 0 and "NotFound" in (err or ""):
            rc = 0

        # Record the outcome
        now = datetime.utcnow() if rc == 0 else None
        async with get_session() as session:
            row = (await session.execute(
                select(ResearchResource).where(
                    ResearchResource.id == r.id
                )
            )).scalars().one()
            if rc == 0:
                row.deleted_at = now
                row.cleanup_status = "done"
            else:
                row.cleanup_status = "failed"
            await session.commit()

        results.append({
            "kind": r.kind, "name": r.name, "namespace": r.namespace,
            "rc": rc, "deleted_at": (now.isoformat() if now else None),
            "err": (err[:200] if err else ""),
        })

    return {
        "summary": f"cleanup walked {len(rows)} resource(s)",
        "items": results,
    }


async def safety_net_cleanup(kc_path: str, research_id: str) -> int:
    """Belt-and-suspenders: if a row is in 'pending' (not 'running' or
    'done'), the resource may still exist on the cluster from a prior
    crashed run. Force-kill it. Returns the number of rows touched.

    Distinct from cleanup_research_resources: this is the
    "find-orphans" path, not the "happy path" path. It is called
    at the start of validate_with_k8s (before the new apply) and
    once at the end (after the happy-path cleanup) as a final
    safety net.
    """
    touched = 0
    async with get_session() as session:
        pending = (await session.execute(
            select(ResearchResource).where(
                ResearchResource.research_id == research_id,
                ResearchResource.cleanup_status == "pending",
            )
        )).scalars().all()

    for r in pending:
        if r.kind == "Namespace":
            _kubectl(kc_path, "delete", "namespace", r.name,
                     "--ignore-not-found=true", "--wait=false", json_out=False)
        else:
            _kubectl(kc_path, "delete", r.kind.lower(), r.name,
                     "-n", r.namespace, "--ignore-not-found=true",
                     "--wait=false", json_out=False)
        async with get_session() as session:
            row = (await session.execute(
                select(ResearchResource).where(
                    ResearchResource.id == r.id
                )
            )).scalars().one()
            row.deleted_at = datetime.utcnow()
            row.cleanup_status = "done"
            await session.commit()
        touched += 1
    return touched