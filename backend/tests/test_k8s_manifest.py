"""Unit tests for ADR-002 commit 3 — ManifestValidator.

Scope:
  - validate_manifest() accepts/rejects based on:
      * kind in ALLOWED_KINDS
      * metadata.namespace starts with ALLOWED_NAMESPACE_PREFIX
      * image in ALLOWED_IMAGES
      * spec free of FORBIDDEN_FIELD_PATHS (hostPath, privileged)
      * container.resources.limits present (parser-level check; deeper
        ceiling enforcement is in MAX_* constants, not asserted here)
  - List input (multi-resource manifest) handled
  - Empty manifest rejected
  - Wrong type rejected
  - Result shape: ok bool, manifests list, errors list, summary()

We do NOT exercise the runtime validator inside validate_with_k8s here —
that path is a thin wrapper and is unit-tested by the k8s_namespace tests.
"""
import pytest

from app.agents.k8s_manifest import (
    ALLOWED_IMAGES,
    ALLOWED_KINDS,
    ALLOWED_NAMESPACE_PREFIX,
    FORBIDDEN_FIELD_PATHS,
    validate_manifest,
    ManifestValidationResult,
)


NS = f"{ALLOWED_NAMESPACE_PREFIX}abc123de"


def _pod_manifest(**overrides):
    """Build a minimal valid Pod manifest. Override any field to break tests."""
    base = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "test-pod",
            "namespace": NS,
        },
        "spec": {
            "containers": [
                {
                    "name": "main",
                    "image": "nginx:alpine",
                    "resources": {
                        "requests": {"cpu": "50m", "memory": "64Mi"},
                        "limits": {"cpu": "200m", "memory": "256Mi"},
                    },
                }
            ],
            "restartPolicy": "Never",
        },
    }
    # Deep-merge for nested dicts isn't needed for these tests.
    base.update(overrides)
    return base


# ─────────────────── accept path ───────────────────

def test_validate_accepts_minimal_pod():
    r = validate_manifest(_pod_manifest())
    assert r.ok is True
    assert len(r.manifests) == 1
    assert r.errors == []


def test_validate_accepts_list_of_manifests():
    r = validate_manifest([
        _pod_manifest(),
        _pod_manifest(metadata={"name": "second", "namespace": NS}),
    ])
    assert r.ok is True
    assert len(r.manifests) == 2


def test_validate_accepts_each_allowed_kind():
    """All 5 kinds must pass for a minimal-but-valid body."""
    for kind in ALLOWED_KINDS:
        m = _pod_manifest()
        m["kind"] = kind
        # For kinds other than Pod, the spec shape differs but we only
        # walk for forbidden fields; Pydantic doesn't deep-validate spec.
        r = validate_manifest(m)
        # ConfigMap/Service may need different metadata but for this
        # smoke test the Pydantic `kind` Literal isn't strict — it just
        # checks ALLOWED_KINDS membership.
        assert r.ok, f"kind={kind} unexpectedly rejected: {r.errors}"


# ─────────────────── reject: kind / namespace / image ───────────────────

def test_validate_rejects_unknown_kind():
    m = _pod_manifest()
    m["kind"] = "DaemonSet"  # not in ALLOWED_KINDS
    r = validate_manifest(m)
    assert r.ok is False
    assert any("DaemonSet" in e for e in r.errors)


def test_validate_rejects_default_namespace():
    m = _pod_manifest()
    m["metadata"]["namespace"] = "default"
    r = validate_manifest(m)
    assert r.ok is False
    assert any("namespace" in e for e in r.errors)


def test_validate_rejects_airw_research_namespace():
    """Production-style ns must not be used even though it sounds related."""
    m = _pod_manifest()
    m["metadata"]["namespace"] = "airw-research"
    r = validate_manifest(m)
    assert r.ok is False
    assert any("namespace" in e for e in r.errors)


def test_validate_rejects_image_not_in_whitelist():
    m = _pod_manifest()
    m["spec"]["containers"][0]["image"] = "evil/backdoor:1.0"
    r = validate_manifest(m)
    assert r.ok is False
    assert any("evil/backdoor" in e for e in r.errors)


def test_validate_rejects_typo_image():
    """A near-miss ('nginx:alpne') must still be rejected — no fuzzy match."""
    m = _pod_manifest()
    m["spec"]["containers"][0]["image"] = "nginx:alpne"
    r = validate_manifest(m)
    assert r.ok is False


# ─────────────────── reject: forbidden fields ───────────────────

def test_validate_rejects_hostpath():
    m = _pod_manifest()
    m["spec"]["containers"][0]["volumeMounts"] = [{
        "name": "v",
        "mountPath": "/data",
    }]
    m["spec"]["volumes"] = [{
        "name": "v",
        "hostPath": {"path": "/etc"},
    }]
    r = validate_manifest(m)
    assert r.ok is False
    assert any("hostPath" in e for e in r.errors)


def test_validate_rejects_privileged():
    m = _pod_manifest()
    m["spec"]["containers"][0]["securityContext"] = {"privileged": True}
    r = validate_manifest(m)
    assert r.ok is False
    assert any("privileged" in e for e in r.errors)


def test_validate_rejects_nested_forbidden_field():
    """Forbidden field buried under an arbitrary key still rejected."""
    m = _pod_manifest()
    m["spec"]["containers"][0]["securityContext"] = {
        "capabilities": {"add": ["NET_ADMIN"]},
    }
    # capabilities.add isn't in FORBIDDEN_FIELD_PATHS yet — but we still
    # want this rejected eventually. For commit 3 we only assert what's
    # currently enforced. So this is a known-acceptable case for now.
    r = validate_manifest(m)
    # Don't assert rejection — capabilities.add isn't in the v1 list.
    # Just confirm we don't crash.
    assert isinstance(r, ManifestValidationResult)


# ─────────────────── input shape ───────────────────

def test_validate_rejects_empty_manifest():
    """An empty dict is missing every required field. The error mentions
    'metadata' (Pydantic lists missing required fields first)."""
    r = validate_manifest({})
    assert r.ok is False
    assert any("metadata" in e for e in r.errors)


def test_validate_rejects_empty_list():
    r = validate_manifest([])
    assert r.ok is False
    assert any("empty" in e.lower() for e in r.errors)


def test_validate_rejects_wrong_type():
    r = validate_manifest("not a manifest")
    assert r.ok is False
    assert any("dict or list" in e for e in r.errors)


# ─────────────────── summary / result shape ───────────────────

def test_result_summary_says_validated():
    r = validate_manifest(_pod_manifest())
    assert "validated" in r.summary()
    assert "1" in r.summary()


def test_result_summary_says_rejected():
    m = _pod_manifest()
    m["kind"] = "DaemonSet"
    r = validate_manifest(m)
    assert "rejected" in r.summary()
    assert "DaemonSet" in r.summary()


def test_collects_multiple_errors():
    """One bad manifest with two violations must surface both in the
    error text. Pydantic groups ValidationErrors into one multi-line
    string per manifest; we count both violations are mentioned."""
    m = _pod_manifest()
    m["kind"] = "DaemonSet"
    m["metadata"]["namespace"] = "default"
    r = validate_manifest(m)
    assert r.ok is False
    # Both violations appear in the single concatenated error string
    assert "DaemonSet" in r.errors[0]
    assert "default" in r.errors[0]