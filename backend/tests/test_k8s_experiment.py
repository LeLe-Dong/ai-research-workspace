"""Unit tests for the K8s experiment planner's self-healing helpers.

These are pure-function tests (no kubectl, no cluster): they lock in the
fixes for the failure modes observed in production runs:

  1. LLM MySQL Deployments overriding the image ENTRYPOINT → CrashLoopBackOff
     (``Failed to find valid data directory``).  ``_validate_and_fix_workload_yaml``
     must rewrite them to the entrypoint-compatible ``args: [mysqld, ...]`` form.
  2. Readiness probes using the split ``-p password`` form (interactive prompt)
     → repaired to ``--password=...``.
  3. Service selectors that don't match any pod template → no endpoints;
     ``_sync_service_selectors`` repairs them.
  4. Database Deployments without a Service → verifier Jobs can't resolve the
     hostname; ``_auto_ensure_services`` synthesizes one.
  5. Verification templates must be one-shot Jobs (logs persist, no restart)
     rather than Deployments with restartPolicy=Always (logs wiped on restart).
"""
import asyncio
import time

import yaml
import pytest

from app.agents import k8s_experiment as ke
from app.agents.k8s_experiment import (
    VERIFY_TEMPLATES,
    _auto_ensure_services,
    _is_namespace_forbidden,
    _make_workload_from_template,
    _run_checks_concurrent,
    _sync_service_selectors,
    _tag_manifest,
    _validate_and_fix_workload_yaml,
    _validate_plan,
)

NS = "airw-research-experiments-test1234"


def _mysql_deployment(name: str, *, command=None, args=None, probe=None) -> dict:
    container = {
        "name": "mysql",
        "image": "registry.adms.io:31542/library/mysql:8.0.32",
        "ports": [{"containerPort": 3306}],
    }
    if command is not None:
        container["command"] = command
    if args is not None:
        container["args"] = args
    if probe is not None:
        container["readinessProbe"] = probe
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "labels": {"app": name}},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {"containers": [container]},
            },
        },
    }


def _workload(name: str, kind: str, doc: dict) -> dict:
    return {
        "name": name,
        "kind": kind,
        "image": "registry.adms.io:31542/library/mysql:8.0.32",
        "replicas": 1,
        "yaml": yaml.safe_dump(doc),
    }


# ───────────── verify templates are one-shot Jobs ─────────────

def test_all_verify_templates_generate_deployments():
    # Deployments (not Jobs): the restricted shared-namespace credential has
    # no RBAC for batch/v1 Jobs. The wrapper keeps the container alive
    # (sleep) so logs persist and side effects run exactly once.
    for key in VERIFY_TEMPLATES:
        name = f"verify-{key.replace('_', '-')}"
        y = _make_workload_from_template(key, name, name, NS, "mysql-master", "mysql-slave")
        doc = yaml.safe_load(y)
        assert doc["kind"] == "Deployment", f"{key}: expected Deployment, got {doc['kind']}"
        spec = doc["spec"]
        assert spec["template"]["spec"]["restartPolicy"] == "Always"
        args = spec["template"]["spec"]["containers"][0]["args"][0]
        assert "sleep 3600" in args, f"{key}: script must not exit (keep-alive)"
        assert "exec sleep" in args
        assert doc["spec"]["template"]["metadata"]["labels"]["app"] == name


# ───────────── entrypoint override repair ─────────────

def test_repairs_shell_wrapped_mysqld():
    doc = _mysql_deployment(
        "mysql-slave",
        command=["/bin/sh", "-c"],
        args=["mysqld --server-id=2 --read_only=ON --gtid_mode=ON"],
    )
    w = _validate_and_fix_workload_yaml(_workload("mysql-slave", "Deployment", doc))
    c = yaml.safe_load(w["yaml"])["spec"]["template"]["spec"]["containers"][0]
    assert "command" not in c, "shell wrapper must be removed so entrypoint init runs"
    assert c["args"] == ["mysqld", "--server-id=2", "--read_only=ON", "--gtid_mode=ON"]


def test_repairs_bare_mysqld_command():
    doc = _mysql_deployment("mysql-master", command=["mysqld", "--server-id=1", "--log_bin=mysql-bin"])
    w = _validate_and_fix_workload_yaml(_workload("mysql-master", "Deployment", doc))
    c = yaml.safe_load(w["yaml"])["spec"]["template"]["spec"]["containers"][0]
    assert "command" not in c
    assert c["args"][0] == "mysqld"
    assert c["args"] == ["mysqld", "--server-id=1", "--log_bin=mysql-bin"]


def test_repairs_split_dash_p_readiness_probe():
    doc = _mysql_deployment(
        "mysql-master",
        probe={"exec": {"command": ["mysqladmin", "ping", "-h", "127.0.0.1", "-p", "airwtest123"]}},
    )
    w = _validate_and_fix_workload_yaml(_workload("mysql-master", "Deployment", doc))
    cmd = yaml.safe_load(w["yaml"])["spec"]["template"]["spec"]["containers"][0]["readinessProbe"]["exec"]["command"]
    assert "--password=airwtest123" in cmd
    assert "-p" not in cmd


def test_leaves_correct_mysqld_args_untouched():
    doc = _mysql_deployment("mysql-master", args=["mysqld", "--server-id=1"])
    w = _validate_and_fix_workload_yaml(_workload("mysql-master", "Deployment", doc))
    c = yaml.safe_load(w["yaml"])["spec"]["template"]["spec"]["containers"][0]
    assert c["args"] == ["mysqld", "--server-id=1"]
    assert "command" not in c


# ───────────── service selector sync ─────────────

def test_sync_service_selectors_fixes_mismatch():
    dep = _mysql_deployment("mysql-master")
    svc = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "mysql-master"},
        "spec": {"selector": {"role": "master"}, "ports": [{"port": 3306}]},
    }
    workloads = [
        _workload("mysql-master", "Deployment", dep),
        _workload("mysql-master", "Service", svc),
    ]
    assert _sync_service_selectors(workloads) == 1
    sel = yaml.safe_load(workloads[1]["yaml"])["spec"]["selector"]
    assert sel == {"app": "mysql-master"}


def test_sync_service_selectors_noop_when_correct():
    dep = _mysql_deployment("mysql-master")
    svc = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "mysql-master"},
        "spec": {"selector": {"app": "mysql-master"}, "ports": [{"port": 3306}]},
    }
    workloads = [
        _workload("mysql-master", "Deployment", dep),
        _workload("mysql-master", "Service", svc),
    ]
    assert _sync_service_selectors(workloads) == 0


# ───────────── auto service creation ─────────────

def test_auto_ensure_services_creates_missing():
    dep = _mysql_deployment("mysql-slave")
    workloads = [_workload("mysql-slave", "Deployment", dep)]
    added = _auto_ensure_services(workloads, NS)
    assert len(added) == 1
    svc = yaml.safe_load(added[0]["yaml"])
    assert svc["kind"] == "Service"
    assert svc["metadata"]["name"] == "mysql-slave"
    assert svc["spec"]["selector"] == {"app": "mysql-slave"}
    assert svc["spec"]["ports"][0]["port"] == 3306


def test_auto_ensure_services_no_duplicate_when_bundled():
    # Multi-doc yaml (Deployment + Service) as produced by _make_mysql_workload
    dep = _mysql_deployment("mysql-master")
    svc = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "mysql-master"},
        "spec": {"selector": {"app": "mysql-master"}, "ports": [{"port": 3306}]},
    }
    bundled = yaml.safe_dump(dep) + "\n---\n" + yaml.safe_dump(svc)
    workloads = [{"name": "mysql-master", "kind": "Deployment", "image": "", "replicas": 1, "yaml": bundled}]
    added = _auto_ensure_services(workloads, NS)
    assert added == [], "must not duplicate a Service already present in the bundle"


# ───────────── redundant LLM verifier dedup ─────────────

def test_validate_plan_drops_redundant_llm_verifier_when_templates_used():
    master = _mysql_deployment("mysql-master")
    slave = _mysql_deployment("mysql-slave")
    plan = {
        "experiment": {"name": "x"},
        "workloads": [
            _workload("mysql-master", "Deployment", master),
            _workload("mysql-slave", "Deployment", slave),
        ],
        "checks": [
            # LLM hand-rolled verifier echoing a marker our template produces.
            {"name": "dup-verifier", "type": "pod_log_match",
             "target": "app=mysql-verify", "expect": "REPLICATION_VERIFIED=true",
             "timeout_sec": 180},
            # A genuine template reference (kept + expanded).
            {"name": "tmpl", "type": "pod_log_match",
             "target": "verify:mysql_write_verify",
             "expect": "REPLICATION_VERIFIED=true", "timeout_sec": 180},
        ],
    }
    out = _validate_plan(plan, NS)
    names = [c["name"] for c in out["checks"]]
    assert "dup-verifier" not in names, "redundant LLM verifier must be dropped"
    assert any(c["target"].startswith("app=verify-") for c in out["checks"]), (
        "template must still expand into a generated verifier target"
    )


def test_validate_plan_keeps_llm_verifier_when_no_templates():
    plan = {
        "experiment": {"name": "x"},
        "workloads": [_workload("mysql-master", "Deployment", _mysql_deployment("mysql-master"))],
        "checks": [
            {"name": "dup-verifier", "type": "pod_log_match",
             "target": "app=mysql-master", "expect": "REPLICATION_VERIFIED=true",
             "timeout_sec": 60},
        ],
    }
    out = _validate_plan(plan, NS)
    # No verify: template used → we must NOT drop the LLM's own check.
    assert any(c["name"] == "dup-verifier" for c in out["checks"])


# ───────────── concurrent check runner ─────────────

def _drain(coro):
    async def _go():
        async for _ in coro:
            pass
    asyncio.run(_go())


def test_run_checks_concurrent_runs_in_parallel(monkeypatch):
    calls = []

    async def fake(kc, ns, target, expect, timeout, progress_cb=None):
        calls.append(target)
        await asyncio.sleep(0.4)
        return {"passed": True, "evidence": f"ok:{target}"}

    monkeypatch.setattr(ke, "_check_pod_log_match", fake)
    plan = {"_auto_labels": [], "checks": [
        {"name": f"c{i}", "type": "pod_log_match", "target": f"app=a{i}",
         "expect": "X", "timeout_sec": 10} for i in range(4)
    ]}
    results = {"checks": []}
    t0 = time.monotonic()
    _drain(_run_checks_concurrent("/k", NS, plan, set(), results))
    dt = time.monotonic() - t0
    # 4 × 0.4s serial == 1.6s; concurrent ≈ 0.4s.
    assert dt < 1.0, f"checks ran serially ({dt:.2f}s), expected parallel"
    assert len(results["checks"]) == 4
    # Results preserved in plan order despite finishing concurrently.
    assert [c["name"] for c in results["checks"]] == ["c0", "c1", "c2", "c3"]


def test_run_checks_concurrent_skips_failed_targets(monkeypatch):
    async def fake(kc, ns, target, expect, timeout, progress_cb=None):
        return {"passed": True, "evidence": "ok"}

    monkeypatch.setattr(ke, "_check_pod_log_match", fake)
    plan = {"_auto_labels": [], "checks": [
        {"name": "c1", "type": "pod_log_match", "target": "app=x",
         "expect": "X", "timeout_sec": 10},
    ]}
    results = {"checks": []}
    _drain(_run_checks_concurrent("/k", NS, plan, {"x"}, results))
    assert results["checks"] == [], "check on failed workload must be skipped, not run"


def test_run_checks_concurrent_preserves_plan_level_skip(monkeypatch):
    async def fake(*a, **kw):  # must never be called for a pre-skipped check
        raise AssertionError("pre-skipped check should not hit the cluster")

    monkeypatch.setattr(ke, "_check_pod_log_match", fake)
    plan = {"_auto_labels": [], "checks": [
        {"name": "c1", "type": "pod_log_match", "target": "app=x", "expect": "X",
         "timeout_sec": 10, "_skipped": True, "evidence": "计划中未部署该资源，跳过"},
    ]}
    results = {"checks": []}
    _drain(_run_checks_concurrent("/k", NS, plan, set(), results))
    assert len(results["checks"]) == 1
    assert results["checks"][0]["_skipped"] is True
    assert results["checks"][0]["passed"] is False


def test_run_checks_concurrent_isolates_exceptions(monkeypatch):
    async def fake(kc, ns, target, expect, timeout, progress_cb=None):
        if target == "app=boom":
            raise RuntimeError("kubectl exploded")
        return {"passed": True, "evidence": "ok"}

    monkeypatch.setattr(ke, "_check_pod_log_match", fake)
    plan = {"_auto_labels": [], "checks": [
        {"name": "boom", "type": "pod_log_match", "target": "app=boom", "expect": "X", "timeout_sec": 10},
        {"name": "fine", "type": "pod_log_match", "target": "app=fine", "expect": "X", "timeout_sec": 10},
    ]}
    results = {"checks": []}
    _drain(_run_checks_concurrent("/k", NS, plan, set(), results))
    by_name = {c["name"]: c for c in results["checks"]}
    assert by_name["boom"]["passed"] is False
    assert "异常" in by_name["boom"]["evidence"]
    assert by_name["fine"]["passed"] is True


# ───────────── shared-namespace fallback (restricted RBAC) ─────────────

def test_is_namespace_forbidden_detects_rbac_rejection():
    msg = ('Error from server (Forbidden): namespaces is forbidden: User '
           '"system:serviceaccount:airw-research:airw-bot" cannot create '
           'resource "namespaces" in API group "" at the cluster scope')
    assert _is_namespace_forbidden(msg)


def test_is_namespace_forbidden_ignores_transient_errors():
    assert not _is_namespace_forbidden("dial tcp 10.6.6.246:6443: i/o timeout")
    assert not _is_namespace_forbidden("")


def test_tag_manifest_labels_every_document():
    dep = _mysql_deployment("mysql-master")
    svc = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "mysql-master"},
        "spec": {"selector": {"app": "mysql-master"}, "ports": [{"port": 3306}]},
    }
    manifest = yaml.safe_dump(dep) + "\n---\n" + yaml.safe_dump(svc)
    tagged = _tag_manifest(manifest, "airw-exp", "abc12345")
    docs = [d for d in yaml.safe_load_all(tagged) if isinstance(d, dict)]
    assert len(docs) == 2
    assert all(d["metadata"]["labels"]["airw-exp"] == "abc12345" for d in docs)


def test_tag_manifest_preserves_existing_labels():
    dep = _mysql_deployment("mysql-master")  # already has app=mysql-master
    tagged = _tag_manifest(yaml.safe_dump(dep), "airw-exp", "deadbeef")
    labels = yaml.safe_load(tagged)["metadata"]["labels"]
    assert labels["app"] == "mysql-master"
    assert labels["airw-exp"] == "deadbeef"


# ───────────── target-ref normalization (bogus auto-workload names) ─────────

def test_normalize_target_ref_strips_known_keys():
    from app.agents.k8s_experiment import _normalize_target_ref
    assert _normalize_target_ref("service=mysql-master") == "mysql-master"
    assert _normalize_target_ref("svc=mysql-slave") == "mysql-slave"
    assert _normalize_target_ref("app=redis") == "redis"
    assert _normalize_target_ref("deployment/redis") == "redis"
    assert _normalize_target_ref("redis") == "redis"


def test_sanitize_k8s_name_coerces_invalid_chars():
    from app.agents.k8s_experiment import _sanitize_k8s_name
    assert _sanitize_k8s_name("service=mysql-master") == "service-mysql-master"
    assert _sanitize_k8s_name("Foo_Bar") == "foo-bar"
    assert _sanitize_k8s_name("") == "wl"


def test_validate_plan_no_bogus_auto_workload_for_service_targets():
    plan = {
        "experiment": {"name": "x"},
        "workloads": [
            _workload("mysql-master", "Deployment", _mysql_deployment("mysql-master")),
        ],
        "checks": [
            # service_ready written with a "service=" prefix must resolve to the
            # existing deployment, NOT spawn an invalid auto-service=... workload.
            {"name": "svc", "type": "service_ready", "target": "service=mysql-master",
             "expect": "true", "timeout_sec": 60},
        ],
    }
    out = _validate_plan(plan, NS)
    names = [w["name"] for w in out["workloads"]]
    assert not any("=" in n for n in names), f"invalid workload names: {names}"
    assert not any(w.get("name", "").startswith("auto-service") for w in out["workloads"])
    assert out["checks"][0]["target"] == "mysql-master"
