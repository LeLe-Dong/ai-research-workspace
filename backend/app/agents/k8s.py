"""K8s environment validator: deploy + verify research recommendations on real cluster.

Called by stepfun agent as the optional final phase ("环境验证").
Uses kubectl with the configured kubeconfig (set via /settings).
"""
import asyncio
import json
import logging
import subprocess
import tempfile
import time
import os
import base64 as _b64
from typing import AsyncIterator

import yaml
from fastapi import HTTPException
from sqlalchemy import select

from app.agents.base import AgentEvent
from app.core.crypto import encrypt, decrypt
from app.db.database import get_session
from app.db.models import K8sCluster

logger = logging.getLogger(__name__)

DEFAULT_NAMESPACE = "airw-research"
EXPERIMENT_NAMESPACE_PREFIX = "airw-research-experiments-"
POD_READY_TIMEOUT_SEC = 30
FALLBACK_KUBECONFIG_PATH = "/root/workspace/ai-research-workspace/backend/kubeconfig.yaml"


def derive_experiment_ns(research_id: str) -> str:
    """Build the per-research experimental namespace name.

    Format: `airw-research-experiments-<8hex>`. The 8-hex suffix is the
    first 8 chars of the research_id (which itself is a 12-hex UUID
    fragment — see Research.gen_id). Short enough to stay inside K8s's
    63-char DNS-label limit, long enough to be unique in practice.
    Deterministic so the same research always maps to the same ns.
    """
    if not research_id:
        raise ValueError("research_id is required for derive_experiment_ns")
    return f"{EXPERIMENT_NAMESPACE_PREFIX}{research_id[:8]}"


def _assert_safe_namespace(ns: str) -> None:
    """Refuse any namespace outside the allow-list.

    Two and only two namespaces are accepted:
      1. `airw-research` — the existing dev/scratch ns.
      2. Anything matching `airw-research-experiments-<short>` — generated
         by derive_experiment_ns().

    Anything else (e.g. `default`, `kube-system`, `prod`, ...) raises
    RuntimeError. This is the hard-coded contract that backs the LLM
    guardrail in the agent prompt: even if the LLM is tricked into
    submitting a manifest pointing at `kube-system`, the backend refuses
    to apply it (the validator in commit 3 also rejects it earlier).
    """
    if ns == DEFAULT_NAMESPACE:
        return
    if ns.startswith(EXPERIMENT_NAMESPACE_PREFIX):
        return
    raise RuntimeError(
        f"validate_with_k8s refused to operate in namespace '{ns}'. "
        f"Allowed: '{DEFAULT_NAMESPACE}' or '{EXPERIMENT_NAMESPACE_PREFIX}*'. "
        f"Use derive_experiment_ns(research_id) for the experimental ns."
    )


async def _load_kubeconfig() -> tuple[str, dict]:
    """Load the first configured K8s cluster. Returns (path_to_tempfile, meta_dict).

    Strategy: prefer DB-stored config (from /settings UI). Fall back to hardcoded
    file for development. Writes a temp kubeconfig that kubectl can use.
    """
    cluster = None
    async with get_session() as session:
        result = await session.execute(select(K8sCluster).order_by(K8sCluster.id))
        cluster = result.scalars().first()

    if not cluster and os.path.exists(FALLBACK_KUBECONFIG_PATH):
        # Fall back to file-based config
        with open(FALLBACK_KUBECONFIG_PATH) as f:
            config = yaml.safe_load(f)
        meta = {"name": config.get("clusters", [{}])[0].get("name", "fallback"), "source": "file"}
        return FALLBACK_KUBECONFIG_PATH, meta

    if not cluster:
        raise RuntimeError(
            "No k8s cluster configured. Add one in /settings → K8s 集群."
        )

    token = decrypt(cluster.bearer_token_enc) if cluster.bearer_token_enc else ""
    ca = decrypt(cluster.ca_cert_enc) if cluster.ca_cert_enc else ""

    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{
            "name": cluster.name,
            "cluster": {
                "server": cluster.api_server,
                "insecure-skip-tls-verify": cluster.skip_tls_verify,
                **({"certificate-authority-data": _b64.b64encode(ca.encode()).decode()} if ca else {}),
            }
        }],
        "contexts": [{
            "name": "default",
            "context": {"cluster": cluster.name, "user": cluster.name, "namespace": cluster.default_namespace}
        }],
        "current-context": "default",
        "users": [{
            "name": cluster.name,
            "user": {"token": token} if token else {},
        }],
    }

    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="airw-k8s-")
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(config, f)

    meta = {"name": cluster.name, "source": "db", "namespace": cluster.default_namespace}
    return path, meta


def _kubectl(kc_path: str, *args: str, json_out: bool = True) -> tuple[int, str, str]:
    """Run kubectl, return (exit_code, stdout, stderr)."""
    cmd = ["kubectl", "--kubeconfig", kc_path, *args]
    if json_out:
        cmd += ["-o", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return proc.returncode, proc.stdout, proc.stderr


def _kubectl_stream(kc_path: str, yaml_manifest: str, *args: str) -> tuple[int, str, str]:
    """kubectl apply -f - with given YAML."""
    cmd = ["kubectl", "--kubeconfig", kc_path, *args, "-f", "-"]
    proc = subprocess.run(cmd, input=yaml_manifest, capture_output=True, text=True, timeout=15)
    return proc.returncode, proc.stdout, proc.stderr


def create_namespace(kc_path: str, ns: str) -> tuple[int, str, str]:
    """Create a namespace. Idempotent: 'AlreadyExists' is treated as rc=0.

    Used by the validate phase to provision the per-research experimental
    ns (airw-research-experiments-<8hex>). Caller must already have run
    _assert_safe_namespace(ns); we re-assert here defensively.

    Why sync subprocess.run (not asyncio.create_subprocess_exec)?
    This is called from a small init step that runs once per validate
    invocation, not in a polling loop — the blocking nature doesn't
    starve SSE the way the sync polling loop did.
    """
    _assert_safe_namespace(ns)
    rc, out, err = _kubectl(kc_path, "create", "namespace", ns, json_out=False)
    if rc != 0 and "AlreadyExists" in (err or ""):
        return 0, "", ""
    return rc, out, err


def delete_namespace(kc_path: str, ns: str) -> tuple[int, str, str]:
    """Delete a namespace. Idempotent: 'NotFound' is treated as rc=0.

    Called from the validate phase's finally block. The 30s timeout is
    longer than the 15s default because namespace teardown waits for
    every resource inside to be removed; 15s is often not enough on a
    busy cluster.
    """
    _assert_safe_namespace(ns)
    cmd = ["kubectl", "--kubeconfig", kc_path, "delete", "namespace", ns,
           "--ignore-not-found=true", "--wait=false"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0 and "NotFound" in (proc.stderr or ""):
        return 0, "", ""
    return proc.returncode, proc.stdout, proc.stderr


async def validate_with_k8s(
    research_id: str,
    title: str,
    goal: str,
    recommendations_md: str,
    research_namespace: str | None = None,
    manifest: dict | list | None = None,
) -> AsyncIterator[AgentEvent]:
    """Spin up a test pod based on research recommendations and report status.

    Steps:
      1. Extract deployment recommendations from report (k8s-related only)
      2. Apply a minimal test pod/manifest in research namespace
      3. Wait for pod to be scheduled (Pending→Running, or stay Pending)
      4. Capture: node assignment, resource requests, status, conditions
      5. Emit AgentEvents for each phase
      6. Cleanup: delete the test pod

    If `manifest` is supplied, it is validated by ManifestValidator (see
    app/agents/k8s_manifest). A failed validation short-circuits with a
    warn-level AgentEvent listing every rejection — the caller learns
    why the manifest was unsafe without the cluster ever seeing it.
    The actual apply path is wired up in commit 4 (which also writes
    research_resources rows); commit 3 only adds the validation step.
    """
    ns = research_namespace or DEFAULT_NAMESPACE
    _assert_safe_namespace(ns)

    # 0. Validate any caller-supplied manifest before touching the cluster.
    if manifest is not None:
        from app.agents.k8s_manifest import validate_manifest
        result = validate_manifest(manifest)
        if not result.ok:
            yield AgentEvent(
                phase="validate", level="warn",
                title="manifest 验证失败",
                detail=result.summary(),
                task_id="task-validate", task_progress=100,
            )
            return
        # Success path: surface a brief ack. Commit 4 will pick this up
        # to actually apply the manifests and write research_resources.
        yield AgentEvent(
            phase="validate", level="info",
            title="manifest 验证通过",
            detail=f"{len(result.manifests)} 个资源 + ns={ns}",
            task_id="task-validate", task_progress=5,
        )

    # 1. Load kubeconfig
    try:
        kc_path, kc_meta = await _load_kubeconfig()
    except Exception as e:
        yield AgentEvent(
            phase="validate", level="error",
            title="未配置 k8s 集群",
            detail=f"在 /settings 添加: {e}",
            task_id="task-validate", task_progress=100,
        )
        return
    yield AgentEvent(
        phase="validate", level="info",
        title=f"加载集群配置: {kc_meta['name']}",
        detail=f"来源: {kc_meta['source']} · 命名空间: {kc_meta.get('namespace', '-')}",
        task_id="task-validate", task_progress=10,
    )

    # 1. Connectivity check
    yield AgentEvent(
        phase="validate", level="info",
        title="连接 k8s 集群",
        detail="测试 API server 连通性",
        task_id="task-validate", task_progress=0,
    )
    rc, out, err = _kubectl(kc_path, "version", "--client=false", json_out=False)
    if rc != 0:
        yield AgentEvent(
            phase="validate", level="error",
            title="k8s 集群不可达",
            detail=f"kubectl 失败: {err[:200]}",
            task_id="task-validate", task_progress=100,
        )
        return
    yield AgentEvent(
        phase="validate", level="success",
        title="k8s 集群连接成功",
        detail=out.strip(),
        task_id="task-validate", task_progress=20,
    )

    # 2. Apply test pod
    yield AgentEvent(
        phase="validate", level="info",
        title="部署测试 Pod",
        detail=f"命名空间 {ns}",
        task_id="task-validate", task_progress=30,
    )
    test_pod = f"""apiVersion: v1
kind: Pod
metadata:
  name: airw-validate-{research_id[:8]}
  namespace: {ns}
  labels:
    airw-research: "{research_id}"
spec:
  restartPolicy: Never
  containers:
  - name: validate
    image: nginx:alpine
    resources:
      requests:
        cpu: "50m"
        memory: "64Mi"
      limits:
        cpu: "200m"
        memory: "256Mi"
"""
    rc, out, err = _kubectl_stream(kc_path, test_pod, "apply")
    if rc != 0:
        yield AgentEvent(
            phase="validate", level="error",
            title="部署失败",
            detail=f"{err[:200]}",
            task_id="task-validate", task_progress=100,
        )
        return
    yield AgentEvent(
        phase="validate", level="success",
        title="测试 Pod 已创建",
        detail=out.strip(),
        task_id="task-validate", task_progress=50,
    )

    # Record the apply in research_resources so commit 4's table-driven
    # cleanup can find it. Failure to record is non-fatal — log and
    # continue (the safety_net path will pick it up if we crashed).
    from app.agents.k8s_cleanup import record_resource
    test_pod_name = f"airw-validate-{research_id[:8]}"
    try:
        await record_resource(
            research_id=research_id,
            kind="Pod",
            name=test_pod_name,
            namespace=ns,
            manifest_json=test_pod,
            cluster_name=kc_meta.get("name"),
        )
    except Exception as e:
        logger.warning(f"record_resource failed (non-fatal): {e}")

    # 3. Wait for scheduling
    yield AgentEvent(
        phase="validate", level="info",
        title="等待 Pod 调度",
        detail="最长 60 秒",
        task_id="task-validate", task_progress=60,
    )
    final_status = "Unknown"
    node_name = ""
    pod_ip = ""
    conditions = []
    start = time.time()
    poll_env = {**os.environ, "KUBECONFIG": kc_path}
    poll_pod_name = f"airw-validate-{research_id[:8]}"
    poll_tick = 0
    while time.time() - start < POD_READY_TIMEOUT_SEC:
        await asyncio.sleep(3)
        poll_tick += 1
        elapsed = int(time.time() - start)
        # Non-blocking kubectl get pod via asyncio subprocess; 5s timeout so
        # we never wedge if the API server hangs.
        try:
            proc = await asyncio.create_subprocess_exec(
                "kubectl", "get", "pod", poll_pod_name,
                "-n", ns, "-o", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=poll_env,
            )
            try:
                out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise RuntimeError("kubectl timed out")
            if proc.returncode != 0:
                continue
            data = json.loads(out_b.decode("utf-8", errors="replace"))
        except (RuntimeError, json.JSONDecodeError, Exception):
            continue
        status = data.get("status", {})
        final_status = status.get("phase", "Unknown")
        pod_ip = status.get("podIP", "")
        spec = data.get("spec", {})
        node_name = spec.get("nodeName", "")
        conditions = [c.get("type", "") + "=" + c.get("status", "")
                      for c in status.get("conditions", [])]
        # Yield a per-tick progress event so SSE / timeline stream keeps
        # moving while we wait (the prior sync-subprocess implementation
        # blocked the loop and the UI sat at task_progress=60 for 60s).
        yield AgentEvent(
            phase="validate", level="info",
            title=f"pod poll t={elapsed}s (#{poll_tick}): {final_status}",
            detail=f"node={node_name or '(未调度)'} ip={pod_ip or '-'} ready=" +
                   ",".join(c for c in conditions if c.startswith("Ready=")) or "-",
            task_id="task-validate",
            task_progress=min(85, 60 + poll_tick * 1),
        )
        if final_status in ("Running", "Succeeded", "Failed"):
            break

    # 4. Capture results
    detail = (
        f"状态: {final_status} · 节点: {node_name or '(未调度)'} · IP: {pod_ip or '-'} · "
        f"耗时: {int(time.time() - start)}s · 条件: {', '.join(conditions) or '-'}"
    )
    level = "success" if final_status in ("Running", "Succeeded") else "warn"
    yield AgentEvent(
        phase="validate", level=level,
        title=f"k8s 验证完成: {final_status}",
        detail=detail,
        task_id="task-validate", task_progress=90,
    )

    # 5. Cleanup — table-driven
    # ADR-002 commit 4: instead of hardcoding `kubectl delete pod`, walk
    # research_resources for this research_id. The Pod we just applied was
    # recorded as a row inside the apply step (we'll add the record call
    # below). The safety-net ensures the row gets deleted even if the
    # caller's iteration was cut short.
    from app.agents.k8s_cleanup import cleanup_research_resources
    cleanup_result = await cleanup_research_resources(kc_path, research_id)
    summary = cleanup_result.get("summary", "cleanup finished")
    failed = [it for it in cleanup_result.get("items", []) if it.get("rc", 0) != 0]
    level = "success" if not failed else "warn"
    yield AgentEvent(
        phase="validate", level=level,
        title="k8s 验证收尾完成",
        detail=f"{summary} · 集群 {node_name or '可访问'}" +
               (f" · {len(failed)} 个资源未清掉" if failed else ""),
        task_id="task-validate", task_progress=100,
    )

    # Cleanup temp kubeconfig
    if kc_meta["source"] == "db":
        try:
            os.unlink(kc_path)
        except OSError:
            pass
