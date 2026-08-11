"""Unit tests for ADR-002 commit 4 — table-driven cleanup.

Scope:
  - record_resource inserts a row with the right shape
  - cleanup_research_resources iterates rows, calls kubectl delete, and
    marks deleted_at + cleanup_status='done' on success
  - Idempotency: row with deleted_at set is skipped (rc=0 silently)
  - Idempotency: kubectl delete returning NotFound is treated as success
  - safety_net_cleanup only touches rows in 'pending' (not 'done' / 'failed')

(RBAC yaml tests removed in part 3/4 of the Phase C integration:
the airw-bot-role.yaml file is gone — Phase C uses the default
airw-research namespace with the existing dev RBAC.)
"""
import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from app.db.database import init_db, get_session
from app.db.models import Research, ResearchResource


def _async_fake(*, rc: int, out: str = "", err: str = ""):
    """Build an async fake matching the _kubectl_async signature.

    Use this as the replacement for monkeypatch.setattr() targets
    that previously pointed at the sync _kubectl helper. _kubectl_async
    is awaited, so the mock must return a coroutine, not a tuple.
    """
    async def fake(*a, **kw):
        return rc, out, err
    return fake


# ─────────────────── record_resource ───────────────────

@pytest.mark.asyncio
async def test_record_resource_inserts_row():
    await init_db()
    async with get_session() as session:
        r = Research(
            title="rr-insert", goal="x", depth="quick", priority="low",
        )
        session.add(r)
        await session.flush()
        rid = r.id
    # Now record
    from app.agents.k8s_cleanup import record_resource
    row_id = await record_resource(
        research_id=rid,
        kind="Pod",
        name="test-pod",
        namespace="airw-research",
        manifest_json='{"kind":"Pod"}',
        cluster_name="dev-cluster",
    )
    assert row_id > 0

    # Verify it was inserted
    async with get_session() as session:
        rows = (await session.execute(
            __import__("sqlalchemy").select(ResearchResource).where(
                ResearchResource.research_id == rid
            )
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].kind == "Pod"
        assert rows[0].name == "test-pod"
        assert rows[0].namespace == "airw-research"
        assert rows[0].cluster_name == "dev-cluster"
        assert rows[0].cleanup_status == "pending"
        assert rows[0].deleted_at is None


# ─────────────────── cleanup_research_resources ───────────────────

@pytest.mark.asyncio
async def test_cleanup_marks_done_on_success(monkeypatch):
    """When kubectl delete returns rc=0, the row gets deleted_at +
    cleanup_status='done'."""
    await init_db()
    async with get_session() as session:
        r = Research(title="c1", goal="x", depth="quick", priority="low")
        session.add(r)
        await session.flush()
        rid = r.id
        rr = ResearchResource(
            research_id=rid, kind="Pod", name="p1",
            namespace="airw-research", manifest_json="",
        )
        session.add(rr)
        await session.commit()

    fake = MagicMock(returncode=0, stdout="pod deleted", stderr="")
    monkeypatch.setattr(
        "app.agents.k8s_cleanup._kubectl_async",
        _async_fake(rc=0, out="pod deleted", err=""),
    )

    from app.agents.k8s_cleanup import cleanup_research_resources
    result = await cleanup_research_resources("/tmp/fake.kubeconfig", rid)
    assert "items" in result
    assert len(result["items"]) == 1
    assert result["items"][0]["rc"] == 0
    assert result["items"][0]["deleted_at"] is not None

    async with get_session() as session:
        from sqlalchemy import select
        row = (await session.execute(
            select(ResearchResource).where(
                ResearchResource.research_id == rid
            )
        )).scalars().one()
        assert row.deleted_at is not None
        assert row.cleanup_status == "done"


@pytest.mark.asyncio
async def test_cleanup_idempotent_on_already_done(monkeypatch):
    """A row that already has deleted_at set is skipped — no kubectl call."""
    await init_db()
    async with get_session() as session:
        r = Research(title="c2", goal="x", depth="quick", priority="low")
        session.add(r)
        await session.flush()
        rid = r.id
        rr = ResearchResource(
            research_id=rid, kind="Pod", name="p2",
            namespace="airw-research",
            deleted_at=datetime.utcnow(),
            cleanup_status="done",
        )
        session.add(rr)
        await session.commit()

    called = []
    async def fake_kubectl_async(*a, **kw):
        called.append(a)
        return 0, "", ""
    monkeypatch.setattr("app.agents.k8s_cleanup._kubectl_async", fake_kubectl_async)

    from app.agents.k8s_cleanup import cleanup_research_resources
    result = await cleanup_research_resources("/tmp/fake.kubeconfig", rid)
    assert result["items"][0]["skipped"] is True
    assert called == [], "kubectl must NOT be called for already-cleaned rows"


@pytest.mark.asyncio
async def test_cleanup_idempotent_on_notfound(monkeypatch):
    """kubectl delete returning rc=1 + 'NotFound' in stderr is treated as success."""
    await init_db()
    async with get_session() as session:
        r = Research(title="c3", goal="x", depth="quick", priority="low")
        session.add(r)
        await session.flush()
        rid = r.id
        rr = ResearchResource(
            research_id=rid, kind="Pod", name="p3",
            namespace="airw-research",
        )
        session.add(rr)
        await session.commit()

    monkeypatch.setattr(
        "app.agents.k8s_cleanup._kubectl_async",
        _async_fake(rc=1, out="", err='Error from server (NotFound): pods "p3" not found\n'),
    )

    from app.agents.k8s_cleanup import cleanup_research_resources
    result = await cleanup_research_resources("/tmp/fake.kubeconfig", rid)
    assert result["items"][0]["rc"] == 0, "NotFound must be treated as success"
    assert result["items"][0]["deleted_at"] is not None


@pytest.mark.asyncio
async def test_cleanup_marks_failed_on_real_error(monkeypatch):
    """kubectl delete returning rc!=0 without NotFound marks row as failed."""
    await init_db()
    async with get_session() as session:
        r = Research(title="c4", goal="x", depth="quick", priority="low")
        session.add(r)
        await session.flush()
        rid = r.id
        rr = ResearchResource(
            research_id=rid, kind="Pod", name="p4",
            namespace="airw-research",
        )
        session.add(rr)
        await session.commit()

    monkeypatch.setattr(
        "app.agents.k8s_cleanup._kubectl_async",
        _async_fake(rc=1, out="", err="forbidden: User cannot list pods"),
    )

    from app.agents.k8s_cleanup import cleanup_research_resources
    result = await cleanup_research_resources("/tmp/fake.kubeconfig", rid)
    assert result["items"][0]["rc"] == 1
    assert result["items"][0]["deleted_at"] is None

    async with get_session() as session:
        from sqlalchemy import select
        row = (await session.execute(
            select(ResearchResource).where(
                ResearchResource.research_id == rid
            )
        )).scalars().one()
        assert row.cleanup_status == "failed"
        assert row.deleted_at is None


# ─────────────────── safety_net_cleanup ───────────────────

@pytest.mark.asyncio
async def test_safety_net_only_touches_pending(monkeypatch):
    """safety_net_cleanup must only act on 'pending' rows, leaving
    'done' / 'failed' / 'running' alone."""
    await init_db()
    async with get_session() as session:
        r = Research(title="sn1", goal="x", depth="quick", priority="low")
        session.add(r)
        await session.flush()
        rid = r.id
        # 3 rows in 3 different states
        session.add(ResearchResource(research_id=rid, kind="Pod", name="p-pending",
                                       namespace="airw-research",
                                       cleanup_status="pending"))
        session.add(ResearchResource(research_id=rid, kind="Pod", name="p-done",
                                       namespace="airw-research",
                                       cleanup_status="done",
                                       deleted_at=datetime.utcnow()))
        session.add(ResearchResource(research_id=rid, kind="Pod", name="p-failed",
                                       namespace="airw-research",
                                       cleanup_status="failed"))
        await session.commit()

    touched = []
    async def fake_kubectl_async(*a, **kw):
        # _kubectl_async signature: _kubectl_async(args, *, timeout, env)
        # args[0] is the args list; args[0][0]='--kubeconfig',
        # args[0][1]=kc_path, args[0][2]='delete', args[0][3]=KIND, args[0][4]=NAME
        touched.append((a[0][3], a[0][4]))  # (kind, name)
        return 0, "", ""
    # NB: monkeypatch must target the import *location*, not the
    # source module. k8s_cleanup did `from app.agents.k8s import
    # _kubectl_async` at module top, so the local binding is what
    # matters inside the cleanup_research_resources function.
    monkeypatch.setattr("app.agents.k8s_cleanup._kubectl_async", fake_kubectl_async)

    from app.agents.k8s_cleanup import safety_net_cleanup
    n = await safety_net_cleanup("/tmp/fake.kubeconfig", rid)
    assert n == 1, f"only the pending row should be touched; got {n}"
    assert touched == [("pod", "p-pending")]
