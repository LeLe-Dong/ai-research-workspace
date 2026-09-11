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
import yaml
import pytest

from app.agents.k8s_experiment import (
    VERIFY_TEMPLATES,
    _auto_ensure_services,
    _make_workload_from_template,
    _sync_service_selectors,
    _validate_and_fix_workload_yaml,
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

def test_all_verify_templates_generate_jobs():
    for key in VERIFY_TEMPLATES:
        name = f"verify-{key.replace('_', '-')}"
        y = _make_workload_from_template(key, name, name, NS, "mysql-master", "mysql-slave")
        doc = yaml.safe_load(y)
        assert doc["kind"] == "Job", f"{key}: expected Job, got {doc['kind']}"
        spec = doc["spec"]
        assert spec["backoffLimit"] == 0, f"{key}: backoffLimit must be 0"
        assert "activeDeadlineSeconds" in spec, f"{key}: missing activeDeadlineSeconds"
        assert spec["template"]["spec"]["restartPolicy"] == "Never", (
            f"{key}: Job pod must use restartPolicy=Never (Deployment=Always wipes logs)"
        )
        # Pods must carry the app label so pod_log_match can select them.
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
