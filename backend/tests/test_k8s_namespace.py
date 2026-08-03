"""Unit tests for ADR-002 commit 2 — ns lifecycle helpers.

Scope:
  - derive_experiment_ns: deterministic, idempotent, fails on empty id
  - _assert_safe_namespace: allow-list enforces, errors have actionable message
  - create_namespace / delete_namespace: subprocess mocked, idempotency +
    safe-namespace guard verified without touching a real cluster

We deliberately do NOT call real kubectl in these tests — the cluster
connection is the operator's domain, not the unit-test domain.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.agents.k8s import (
    DEFAULT_NAMESPACE,
    EXPERIMENT_NAMESPACE_PREFIX,
    derive_experiment_ns,
    _assert_safe_namespace,
    create_namespace,
    delete_namespace,
)


# ─────────────────── derive_experiment_ns ───────────────────

def test_derive_experiment_ns_format():
    ns = derive_experiment_ns("abc123def456")
    assert ns.startswith(EXPERIMENT_NAMESPACE_PREFIX)
    assert ns == f"{EXPERIMENT_NAMESPACE_PREFIX}abc123de"   # 8-char slice
    assert len(ns) <= 63  # k8s DNS-1123 label limit


def test_derive_experiment_ns_deterministic():
    """Same id → same ns across calls."""
    a = derive_experiment_ns("44403fa2b571")
    b = derive_experiment_ns("44403fa2b571")
    assert a == b


def test_derive_experiment_ns_unique_per_research():
    """Different ids → different ns."""
    a = derive_experiment_ns("44403fa2b571")
    b = derive_experiment_ns("99e3a5a06069")
    assert a != b


def test_derive_experiment_ns_rejects_empty():
    with pytest.raises(ValueError, match="research_id is required"):
        derive_experiment_ns("")


# ─────────────────── _assert_safe_namespace ───────────────────

def test_assert_safe_namespace_accepts_default():
    # Must not raise
    _assert_safe_namespace(DEFAULT_NAMESPACE)


def test_assert_safe_namespace_accepts_experiment_prefix():
    ns = derive_experiment_ns("44403fa2b571")
    _assert_safe_namespace(ns)  # must not raise


def test_assert_safe_namespace_rejects_kube_system():
    with pytest.raises(RuntimeError, match="kube-system"):
        _assert_safe_namespace("kube-system")


def test_assert_safe_namespace_rejects_default():
    with pytest.raises(RuntimeError, match="default"):
        _assert_safe_namespace("default")


def test_assert_safe_namespace_rejects_random_prod():
    with pytest.raises(RuntimeError, match="prod"):
        _assert_safe_namespace("prod")


def test_assert_safe_namespace_error_is_actionable():
    """The error message must mention BOTH allow-list entries so the caller
    can self-correct without reading source."""
    try:
        _assert_safe_namespace("kube-system")
    except RuntimeError as e:
        msg = str(e)
        assert DEFAULT_NAMESPACE in msg, f"error must mention {DEFAULT_NAMESPACE}: {msg}"
        assert EXPERIMENT_NAMESPACE_PREFIX in msg, (
            f"error must mention prefix {EXPERIMENT_NAMESPACE_PREFIX}: {msg}"
        )


# ─────────────────── create_namespace / delete_namespace ───────────────────

def test_create_namespace_succeeds(monkeypatch):
    """Mock kubectl, verify the right subprocess call is made."""
    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = "namespace/foo created\n"
    fake_proc.stderr = ""
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_proc)
    rc, out, err = create_namespace("/tmp/fake.kubeconfig", "airw-research-experiments-abc123de")
    assert rc == 0
    assert "created" in out


def test_create_namespace_idempotent_on_already_exists(monkeypatch):
    """Second call against the same ns must not error — treat 'AlreadyExists' as success."""
    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.stdout = ""
    fake_proc.stderr = 'Error from server (AlreadyExists): namespace "foo" already exists\n'
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_proc)
    rc, out, err = create_namespace("/tmp/fake.kubeconfig", "airw-research-experiments-abc123de")
    assert rc == 0, f"idempotent create must return rc=0, got {rc}"
    assert err == ""


def test_create_namespace_refuses_unsafe_ns(monkeypatch):
    """Calling create_namespace with a forbidden ns raises BEFORE any subprocess call."""
    calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: calls.append(a) or MagicMock(returncode=0),
    )
    with pytest.raises(RuntimeError, match="kube-system"):
        create_namespace("/tmp/fake.kubeconfig", "kube-system")
    assert calls == [], f"subprocess must NOT be called for unsafe ns; got {calls}"


def test_delete_namespace_succeeds(monkeypatch):
    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = 'namespace "foo" deleted\n'
    fake_proc.stderr = ""
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_proc)
    rc, out, err = delete_namespace("/tmp/fake.kubeconfig", "airw-research-experiments-abc123de")
    assert rc == 0


def test_delete_namespace_idempotent_on_not_found(monkeypatch):
    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.stdout = ""
    fake_proc.stderr = 'Error from server (NotFound): namespaces "foo" not found\n'
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_proc)
    rc, out, err = delete_namespace("/tmp/fake.kubeconfig", "airw-research-experiments-abc123de")
    assert rc == 0


def test_delete_namespace_refuses_unsafe_ns(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: calls.append(a) or MagicMock(returncode=0),
    )
    with pytest.raises(RuntimeError, match="default"):
        delete_namespace("/tmp/fake.kubeconfig", "default")
    assert calls == [], "subprocess must NOT be called for unsafe ns"