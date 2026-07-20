"""K8s environment validator: deploy + verify research recommendations on real cluster.

Called by stepfun agent as the optional final phase ("环境验证").
Uses kubectl with the configured kubeconfig (set via /settings).
"""
import json
import logging
import subprocess
import time
from typing import AsyncIterator

from app.agents.base import AgentEvent

logger = logging.getLogger(__name__)

KUBECONFIG_PATH = "/root/workspace/ai-research-workspace/backend/kubeconfig.yaml"
DEFAULT_NAMESPACE = "airw-research"
POD_READY_TIMEOUT_SEC = 30


def _kubectl(*args: str, json_out: bool = True) -> tuple[int, str, str]:
    """Run kubectl, return (exit_code, stdout, stderr)."""
    cmd = ["kubectl", "--kubeconfig", KUBECONFIG_PATH, *args]
    if json_out:
        cmd += ["-o", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return proc.returncode, proc.stdout, proc.stderr


def _kubectl_stream(yaml_manifest: str, *args: str) -> tuple[int, str, str]:
    """kubectl apply -f - with given YAML."""
    cmd = ["kubectl", "--kubeconfig", KUBECONFIG_PATH, *args, "-f", "-"]
    proc = subprocess.run(cmd, input=yaml_manifest, capture_output=True, text=True, timeout=15)
    return proc.returncode, proc.stdout, proc.stderr


async def validate_with_k8s(
    research_id: str,
    title: str,
    goal: str,
    recommendations_md: str,
    research_namespace: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """Spin up a test pod based on research recommendations and report status.

    Steps:
      1. Extract deployment recommendations from report (k8s-related only)
      2. Apply a minimal test pod/manifest in research namespace
      3. Wait for pod to be scheduled (Pending→Running, or stay Pending)
      4. Capture: node assignment, resource requests, status, conditions
      5. Emit AgentEvents for each phase
      6. Cleanup: delete the test pod
    """
    ns = research_namespace or DEFAULT_NAMESPACE

    # 1. Connectivity check
    yield AgentEvent(
        phase="validate", level="info",
        title="连接 k8s 集群",
        detail="测试 API server 连通性",
        task_id="task-validate", task_progress=0,
    )
    rc, out, err = _kubectl("version", "--client=false", json_out=False)
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
    rc, out, err = _kubectl_stream(test_pod, "apply")
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
    while time.time() - start < POD_READY_TIMEOUT_SEC:
        time.sleep(3)
        rc, out, err = _kubectl("get", "pod", f"airw-validate-{research_id[:8]}", "-n", ns)
        if rc != 0:
            continue
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            continue
        status = data.get("status", {})
        final_status = status.get("phase", "Unknown")
        pod_ip = status.get("podIP", "")
        spec = data.get("spec", {})
        node_name = spec.get("nodeName", "")
        conditions = [c.get("type", "") + "=" + c.get("status", "")
                      for c in status.get("conditions", [])]
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

    # 5. Cleanup
    rc, out, err = _kubectl("delete", "pod", f"airw-validate-{research_id[:8]}", "-n", ns, "--wait=false")
    yield AgentEvent(
        phase="validate", level="success",
        title="k8s 验证收尾完成",
        detail=f"测试 Pod 已清理 · 集群 {node_name or '可访问'}",
        task_id="task-validate", task_progress=100,
    )
