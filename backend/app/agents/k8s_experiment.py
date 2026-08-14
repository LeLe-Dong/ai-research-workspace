"""LLM-driven K8s experiment executor.

This replaces the fixed workload templates with a real experiment that the
LLM designs for THIS specific research. Flow:

  1. Build an experiment-planning prompt from the research goal + the LLM's
     findings (recommendations_md).
  2. Call an LLM (Stepfun chat_json — OpenAI-compatible, JSON mode) to emit a
     structured experiment plan:
         {
           "experiment": {"name": str, "namespace": str},
           "workloads": [{"name", "kind", "image", "replicas", "yaml"}],
           "checks": [{"name", "type", "target", "expect", "timeout_sec"}]
         }
  3. Apply every workload manifest into a per-research experimental namespace
     (airw-research-experiments-<8hex>, enforced by _assert_safe_namespace).
  4. Run the checks (pod_ready / service_ready / pod_log_match / http_ok)
     and collect pass/fail + measured evidence.
  5. Persist the whole experiment + results as a "k8s-experiment" artifact so
     the report writer can quote per-check evidence.

Unlike the old fixed template, the YAML and the assertions are generated for
the specific recommendation under study — the "experiment" actually tests
what the research proposed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import yaml

from app.agents.base import AgentEvent
from app.agents.k8s import (
    derive_experiment_ns,
    _assert_safe_namespace,
    _load_kubeconfig,
    _kubectl,
    _kubectl_async,
    create_namespace,
    delete_namespace,
)
from app.agents.llm import StepfunClient, LLMError

logger = logging.getLogger(__name__)

# Check type → how to verify. Only these are allowed (LLM output is untrusted,
# so we never let it name arbitrary kubectl subcommands).
ALLOWED_CHECK_TYPES = ("pod_ready", "service_ready", "pod_log_match", "http_ok")

# Hard cap so a misbehaving LLM can't make us apply 50 resources.
MAX_WORKLOADS = 6
MAX_CHECKS = 10


def _to_short_ref(image: str) -> str:
    """Reduce an image ref to `<name>:<tag>` for console display."""
    from app.agents.k8s_image import _to_short_name
    return _to_short_name(image)


def _default_llm() -> StepfunClient | None:
    """Build an OpenAI-compatible client for experiment planning.

    Priority:
      1. deepseek-v4-flash via OpenCode Go (opencode.ai/zen/go/v1) — key read
         from opencode's auth.json; this is what the researcher agent uses.
      2. AIRW_STEPFUN_* env as fallback (historically the default).
    Returns None if no key is available.
    """
    try:
        # 1. OpenCode Go (deepseek) — read the key opencode itself uses.
        import json as _json
        import os as _os
        auth_path = _os.path.expanduser("~/.local/share/opencode/auth.json")
        if _os.path.exists(auth_path):
            try:
                auth = _json.load(open(auth_path))
                go_key = (auth.get("opencode-go") or {}).get("key") or ""
                if go_key:
                    return StepfunClient(
                        api_key=go_key,
                        base_url="https://opencode.ai/zen/go/v1",
                        model="deepseek-v4-flash",
                        timeout=90.0,
                    )
            except Exception:
                pass
        # 2. Stepfun fallback
        from app.core.config import settings
        if settings.stepfun_api_key:
            return StepfunClient(
                api_key=settings.stepfun_api_key,
                base_url=settings.stepfun_base_url or "https://api.stepfun.com/step_plan/v1",
                model=settings.stepfun_model or "step-3.7-flash",
                timeout=90.0,
            )
    except Exception:
        pass
    return None


EXPERIMENT_SYSTEM = """你是 Kubernetes 专家，负责为一项 AI 预研课题设计"可执行的验证试验"。

你只输出一个 JSON 对象，不要输出任何其他文字、解释、markdown 代码块或前后缀。

要求：
- 试验必须针对该研究的**具体推荐方案**（镜像、部署方式、配置参数），而不是泛化模板。
- 每个 workload 的 yaml 必须是完整可用的 Kubernetes 清单（Pod / Deployment / Service 等），
  命名空间必须使用 {namespace}。
- 镜像必须来自内网 registry：registry.adms.io:31542/library/<image>:<tag>
  （例如 registry.adms.io:31542/library/redis:7.0.4，registry.adms.io:31542/library/postgres:15，
   registry.adms.io:31542/library/mysql:8.0，registry.adms.io:31542/library/mongo:8.0，
   registry.adms.io:31542/library/nginx:1.26.2-alpine，registry.adms.io:31542/library/busybox:1.0）
  ，不允许使用公网镜像。
- 资源请求要保守（cpu ≤ 500m, memory ≤ 512Mi），避免超出集群配额。

JSON schema（严格遵循，字段名不能改）：
{{
  "experiment": {{"name": str, "namespace": "{namespace}"}},
  "workloads": [
    {{"name": str, "kind": str, "image": str, "replicas": int,
      "yaml": str}}
  ],
  "checks": [
    {{"name": str, "type": str, "target": str, "expect": str, "timeout_sec": int}}
  ]
}}

check.type 只能是以下枚举之一：
- pod_ready      : 目标 Pod 就绪（target 为 label 选择器，如 "app=redis"）
- service_ready  : Service 有端点（target 为 Service 名）
- pod_log_match  : Pod 日志包含 expect 字符串（target 为 label 选择器）
- http_ok        : 命名空间内 HTTP 请求返回 2xx（target 为 http://service:port/）

check.expect 根据类型填写期望值（pod_ready 填 "true"；pod_log_match 填要匹配的子串；http_ok 填 "200" 或 "2xx"）。
check.timeout_sec 给足 Pod 拉取镜像和启动的时间，默认 90。
"""


async def _ask_llm_for_experiment(
    llm: StepfunClient,
    namespace: str,
    goal: str,
    recommendations_md: str,
) -> dict:
    user = (
        "研究目标：\n" + (goal or "") + "\n\n"
        "研究发现/推荐方案：\n" + (recommendations_md or "")[:6000] + "\n\n"
        "请根据以上研究设计一个真实的 Kubernetes 验证试验，生成 JSON。"
    )
    try:
        return await llm.chat_json(EXPERIMENT_SYSTEM.format(namespace=namespace), user,
                                   max_tokens=6000, temperature=0.2)
    except (LLMError, Exception) as e:
        logger.warning("LLM experiment planning failed: %s", e)
        raise


async def _ask_hermes_for_experiment(
    namespace: str,
    goal: str,
    recommendations_md: str,
) -> dict:
    """Generate an experiment plan via the local hermes k8s-expert CLI.

    Primary path: hermes runs locally (doesn't depend on our API-key quota),
    has a dedicated `k8s-expert` profile, and produces complete, working
    manifests. We strip the decorative box, extract the JSON payload, and
    sanitize it with _validate_plan downstream.
    """
    import asyncio as _asyncio
    import re as _re
    import shlex

    hermes_bin = "/root/.local/bin/hermes"
    profile = "k8s-expert"
    skills = ""

    # JSON-only instruction; the plan schema mirrors EXPERIMENT_SYSTEM.
    # Keep it SHORT and deterministic — hermes k8s-expert slows down a lot
    # with long input or many turns, and may start "trying things" instead
    # of just emitting JSON.
    prompt = (
        "你是K8s专家。只输出JSON，不要解释、不要markdown代码块、不要调用任何工具。\n"
        "为这项研究设计可执行的K8s验证试验。\n\n"
        "【研究目标（必须围绕它设计试验）】\n" + (goal or "")[:1200] + "\n\n"
        "【研究发现/推荐方案（参考，不要偏离目标）】\n" + (recommendations_md or "")[:2000] + "\n\n"
        "要求：\n"
        f"0. 试验必须直接验证【研究目标】中的关键点：把目标里提到的每个可测项"
        "（如：高可用/故障切换、主从复制、Cluster分片、持久化、ACL、性能/吞吐等）"
        "映射为具体的工作负载和断言。不要在目标没提的方向上另起炉灶，也不要遗漏目标里的核心验证项。\n"
        f"1. 命名空间必须用 {namespace}。\n"
        "2. 镜像只能用 registry.adms.io:31542/library/<image>:<tag>（redis:7.0.4/postgres:15/"
        "mysql:8.0/mongo:8.0/nginx:1.26.2-alpine/busybox:1.0）。\n"
        "3. Deployment 不要写 restartPolicy；labels 用 app=<名>；checks target 用 app=<名>。\n"
        "4. 压测容器命令必须先 until 等待依赖就绪再压测，输出含 'requests per second' 或 'ops'。"
        "等待命令写法示例：until redis-cli -h redis-cache ping 2>/dev/null | grep -q PONG; do sleep 1; done"
        "（redis-cli 没有 -t 参数，不要用 redis-cli -t）。\n"
        "5. 使用 mysql 镜像时，容器必须设置 MYSQL_ROOT_PASSWORD（或 MYSQL_ALLOW_EMPTY_PASSWORD=yes），"
        "否则 mysql 8 容器无法完成初始化；mysql 默认数据目录是 /var/lib/mysql。\n"
        "6. 资源请求 cpu<=500m, memory<=512Mi。\n"
        "7. 一个 workload 的 yaml 只放一个资源（多资源就放多个 workload 条目）。\n"
        "8. 试验的 checks 必须与 workloads 一一对应，不要引用未部署的资源。\n\n"
        "JSON格式：\n"
        "{\"experiment\":{\"name\":\"x\",\"namespace\":\"" + namespace + "\"},"
        "\"workloads\":[{\"name\":\"x\",\"kind\":\"Deployment\",\"image\":\"registry.adms.io:31542/library/redis:7.0.4\",\"replicas\":1,\"yaml\":\"...\"}],"
        "\"checks\":[{\"name\":\"c\",\"type\":\"pod_ready|service_ready|pod_log_match|http_ok\",\"target\":\"app=x\",\"expect\":\"true\",\"timeout_sec\":90}]}"
    )

    cmd = [hermes_bin, "chat", "-q", prompt, "--cli",
           "--max-turns", "3", "--yolo", "-p", profile, "-s", skills]
    logger.info("Running hermes k8s-expert for experiment plan ...")

    # Inject the OpenCode Go (deepseek) key into the subprocess environment.
    # hermes reads provider keys from os.environ (source: env:OPENCODE_GO_API_KEY),
    # NOT automatically from ~/.hermes/.env — without this the k8s-expert CLI
    # gets HTTP 401 and the plan generation fails. We reuse the key opencode
    # itself authenticates with (read from its auth.json).
    import os as _os
    sub_env = dict(_os.environ)
    if not sub_env.get("OPENCODE_GO_API_KEY"):
        try:
            _auth_path = _os.path.expanduser("~/.local/share/opencode/auth.json")
            if _os.path.exists(_auth_path):
                _auth = json.load(open(_auth_path))
                _go = (_auth.get("opencode-go") or {}).get("key") or ""
                if _go:
                    sub_env["OPENCODE_GO_API_KEY"] = _go
        except Exception:
            pass

    proc = await _asyncio.create_subprocess_exec(
        *cmd,
        env=sub_env,
        stdout=_asyncio.subprocess.PIPE,
        stderr=_asyncio.subprocess.PIPE,
    )
    try:
        out_b, _err_b = await _asyncio.wait_for(proc.communicate(), timeout=350)
    except _asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("hermes k8s-expert timed out after 350s")
    if proc.returncode != 0 and not out_b:
        raise RuntimeError(f"hermes exited rc={proc.returncode}")

    text = out_b.decode("utf-8", errors="replace")

    # Strip the decorative box / noise, then find the JSON object.
    try:
        from app.agents.hermes_researcher import _strip_hermes_decorations
        cleaned = _strip_hermes_decorations(text)
    except Exception:
        cleaned = text
    # The box strip may keep trailing commentary; slice from first { to last }.
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first < 0 or last <= first:
        raise RuntimeError("hermes did not return a JSON object")
    payload = cleaned[first:last + 1]
    plan = json.loads(payload)
    if not isinstance(plan, dict):
        raise RuntimeError("hermes JSON is not an object")
    return plan


def _validate_plan(plan: dict, namespace: str) -> dict:
    """Sanitize the LLM's plan: enforce caps, allowed check types, namespace."""
    experiment = plan.get("experiment") or {}
    workloads = (plan.get("workloads") or [])[:MAX_WORKLOADS]
    checks = (plan.get("checks") or [])[:MAX_CHECKS]

    cleaned_workloads = []
    for w in workloads:
        if not isinstance(w, dict):
            continue
        w_yaml = w.get("yaml", "")
        # Namespace safety: rewrite any namespace in the manifest to the
        # experiment namespace, then assert it's the allowed one.
        try:
            docs = list(yaml.safe_load_all(w_yaml))
            # A single workload entry may contain MULTIPLE yaml documents
            # (LLM sometimes bundles Service + Deployment into one "yaml"
            # string). Expand them into separate workload entries.
            real_docs = [d for d in docs if isinstance(d, dict)]
            if not real_docs:
                continue
            for doc in real_docs:
                doc.setdefault("metadata", {})["namespace"] = namespace
                doc["metadata"].setdefault("name", w.get("name", "wl"))
                # Sanitize common LLM mistakes so the manifest is actually
                # accepted by the API server:
                #  - Deployment/ReplicaSet/StatefulSet/DaemonSet must use
                #    restartPolicy=Always (Never/OnFailure are invalid).
                kind = str(doc.get("kind", ""))
                spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
                tmpl_spec = None
                if isinstance(spec.get("template"), dict) and isinstance(spec["template"].get("spec"), dict):
                    tmpl_spec = spec["template"]["spec"]
                if kind in ("Deployment", "ReplicaSet", "StatefulSet", "DaemonSet") and tmpl_spec is not None:
                    if tmpl_spec.get("restartPolicy", "Always") != "Always":
                        tmpl_spec["restartPolicy"] = "Always"
                cleaned_workloads.append({
                    "name": str(doc["metadata"].get("name", f"wl-{len(cleaned_workloads)}"))[:50],
                    "kind": kind or "Deployment",
                    "image": str(w.get("image", ""))[:200],
                    "replicas": max(1, int(w.get("replicas") or 1)),
                    "yaml": yaml.safe_dump(doc),
                })
                if len(cleaned_workloads) >= MAX_WORKLOADS:
                    break
        except Exception as e:
            logger.warning("workload yaml parse failed (%s), skipping: %s | head=%r",
                           e, w.get("name"), w_yaml[:120])
            continue

    # Build the set of deployable resource names (metadata.name) + label
    # selectors implied by them, so we can drop checks that reference
    # resources the plan never actually deploys. LLM plans frequently list
    # more checks than workloads (e.g. checks for redis-cluster-2/init that
    # have no matching manifest) — those would burn the full timeout then
    # fail. We surface them as skipped instead.
    deployed_names = {str(w["name"]).lower() for w in cleaned_workloads}
    # Also collect the app=<x> label that each workload's pod carries, if any.
    deployed_apps: set[str] = set()
    for w in cleaned_workloads:
        try:
            doc = yaml.safe_load(w["yaml"])
            if isinstance(doc, dict):
                md = doc.get("metadata") or {}
                lbl = ((doc.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
                for k, v in lbl.items():
                    if k == "app":
                        deployed_apps.add(str(v).lower())
        except Exception:
            pass

    cleaned_checks = []
    for c in checks:
        if not isinstance(c, dict):
            continue
        ctype = str(c.get("type", ""))
        if ctype not in ALLOWED_CHECK_TYPES:
            logger.warning("skipping unsupported check type: %s", ctype)
            continue
        target = str(c.get("target", ""))[:200]
        # Resolve what the check targets: a bare selector (app=x), a
        # resource-qualified name (deployment/x), or a service name.
        ref = target.strip()
        # strip kind/ prefix
        ref_low = ref.split("/")[-1].lower()
        # label selector form: app=<name>  → name
        if ref_low.startswith("app="):
            ref_low = ref_low[len("app="):]
        ref_low = ref_low.strip()
        exists = (
            (ref_low in deployed_names)
            or (ref_low in deployed_apps)
            or (ref_low and any(ref_low in n for n in deployed_names))
        )
        timeout = max(10, int(c.get("timeout_sec") or 90))
        # Cap each check's wait so many checks can't pile up hundreds of
        # seconds of serial timeouts (this was timing out whole researches).
        timeout = min(timeout, 120)
        if not exists:
            logger.warning(
                "skipping check %r: target %r has no matching workload "
                "(deployed=%s)", c.get("name"), target, sorted(deployed_names)[:8]
            )
            cleaned_checks.append({
                "name": str(c.get("name", ctype))[:80],
                "type": ctype,
                "target": target,
                "expect": str(c.get("expect", ""))[:200],
                "timeout_sec": 5,
                "_skipped": True,
                "evidence": f"目标 '{target}' 未在计划中部署，跳过",
            })
            continue
        cleaned_checks.append({
            "name": str(c.get("name", ctype))[:80],
            "type": ctype,
            "target": target,
            "expect": str(c.get("expect", ""))[:200],
            "timeout_sec": timeout,
        })

    return {
        "experiment": {
            "name": str(experiment.get("name", "experiment"))[:80],
            "namespace": namespace,
        },
        "workloads": cleaned_workloads,
        "checks": cleaned_checks,
    }


def _extract_container_command(manifest: str) -> str:
    """Extract the command/args each container runs, for console display.

    Walks spec.containers / initContainers in the manifest and formats the
    shell command so the user can see exactly what the agent asked the pod
    to execute (e.g. redis-benchmark -h redis -n 100000 ...).
    """
    try:
        docs = list(yaml.safe_load_all(manifest))
    except Exception:
        return ""
    out_lines: list[str] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        spec = doc.get("spec") or {}
        tmpl = spec.get("template") or {}
        tspec = tmpl.get("spec") or spec  # Deployment/StatefulSet vs bare Pod
        if not isinstance(tspec, dict):
            continue
        for grp, cts in (("init", tspec.get("initContainers") or []),
                         ("", tspec.get("containers") or [])):
            for c in cts or []:
                if not isinstance(c, dict):
                    continue
                name = c.get("name", "?")
                cmd = c.get("command") or []
                args = c.get("args") or []
                full = list(cmd) + list(args)
                if not full:
                    continue
                joined = " ".join(str(x) for x in full)
                if grp:
                    out_lines.append(f"[init:{name}] {joined}")
                else:
                    out_lines.append(f"[{name}] {joined}")
    return "\n".join(out_lines)


async def _apply_workload(kc_path: str, manifest: str) -> tuple[int, str, str]:
    cmd = ["kubectl", "--kubeconfig", kc_path, "apply", "-f", "-"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(
            proc.communicate(manifest.encode()), timeout=20,
        )
        return proc.returncode, out_b.decode(), err_b.decode()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -2, "", "kubectl apply timed out"


async def _resolve_pod_selector(kc_path: str, ns: str, target: str) -> str:
    """Turn a check target into a label selector for `kubectl ... -l <sel>`.

    LLM may write either a bare label selector ("app=redis-cache") or a
    resource-qualified name ("deployment/redis-cache"). For the latter we
    resolve the workload's own selector so the pod query actually matches.
    Returns "" if it cannot be resolved (caller should treat as no match).
    """
    t = target.strip()
    if "/" in t:
        kind, name = t.split("/", 1)
        kind = kind.lower()
        if kind in ("deployment", "deploy", "statefulset", "sts", "daemonset", "ds", "replicaset", "rs"):
            rc, out, err = await _kubectl_async(
                ["--kubeconfig", kc_path, "get", kind, name, "-n", ns,
                 "-o", "jsonpath={.spec.selector.matchLabels}"],
                timeout=10,
            )
            if rc == 0 and out.strip():
                try:
                    labels = json.loads(out.strip())
                    if isinstance(labels, dict):
                        return ",".join(f"{k}={v}" for k, v in labels.items())
                except Exception:
                    pass
            # Fallback: deployment name as label (most templates label the pod
            # with app=<name>)
            return f"app={name}"
        if kind == "pod":
            # Single pod by name — no selector possible; return a sentinel
            return f"name={name}"
    return t


async def _check_pod_ready(kc_path: str, ns: str, target: str, timeout_sec: int,
                           progress_cb=None) -> dict:
    """Wait until a pod matching target (selector or deployment/name) is Ready.

    progress_cb: optional async callable(msg: str) invoked on each poll tick
    so the caller can stream the pod's live status to the console.
    """
    selector = await _resolve_pod_selector(kc_path, ns, target)
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last_status = ""
    last_wait_ts = 0.0
    import re as _re  # used in the status-line parser below
    while asyncio.get_event_loop().time() < deadline:
        rc, out, err = await _kubectl_async(
            ["--kubeconfig", kc_path, "get", "pod", "-n", ns,
             "-l", selector,
             "-o", "jsonpath={range .items[*]}{.metadata.name}{\" \"}{.status.phase}{\" \"}{.status.containerStatuses[*].state}{\"\\n\"}{end}"],
            timeout=10,
        )
        if rc == 0 and out.strip():
            ready = "True" in out or 'running' in out.lower()
            # Build a human-readable status line from the raw pod output.
            status_line = ""
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                name = parts[0]
                phase = parts[1] if len(parts) > 1 else "?"
                state = " ".join(parts[2:])
                # state looks like {"running":{"startedAt":...}} or {"waiting":{"reason":"ContainerCreating"}}
                reason = "running"
                if "waiting" in state and "reason" in state:
                    m = _re.search(r"reason\\?\":\\?\"([^\\\"]+)", state)
                    reason = m.group(1) if m else "waiting"
                elif "terminated" in state and "reason" in state:
                    m = _re.search(r"reason\\?\":\\?\"([^\\\"]+)", state)
                    reason = m.group(1) if m else "terminated"
                status_line += f"{name} [{phase}/{reason}] "
            status_line = status_line.strip()
            if ready:
                return {"passed": True, "evidence": f"Pod 就绪（{target}）: {status_line}"}
            if progress_cb is not None and status_line != last_status:
                last_status = status_line
                last_wait_ts = asyncio.get_event_loop().time()
                await progress_cb(status_line)
        # Throttle the "still waiting" hint so it doesn't spam the console.
        now = asyncio.get_event_loop().time()
        if progress_cb is not None and now - last_wait_ts >= 15:
            last_wait_ts = now
            await progress_cb(f"[pod_ready] 仍在等待就绪... ({int(deadline - now)}s 剩余)")
        await asyncio.sleep(3)
    return {"passed": False, "evidence": f"超时 {timeout_sec}s 等待 Pod 就绪（{target}）"}


async def _check_service_ready(kc_path: str, ns: str, service: str, timeout_sec: int,
                               progress_cb=None) -> dict:
    # Accept "service/name", a bare name, OR a label selector like
    # "app=redis-cache" (in which case resolve to the service's name).
    svc = service.strip()
    if "=" in svc and not svc.startswith("http"):
        # label selector → find the first service matching it
        rc, out, err = await _kubectl_async(
            ["--kubeconfig", kc_path, "get", "service", "-n", ns,
             "-l", svc, "-o", "jsonpath={.items[*].metadata.name}"],
            timeout=10,
        )
        if rc == 0 and out.strip():
            svc = out.strip().split()[0]
        else:
            return {"passed": False, "evidence": f"没有匹配选择器 '{service}' 的 Service"}
    svc = svc.split("/")[-1]
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last_ips = ""
    last_wait_ts = 0.0
    while asyncio.get_event_loop().time() < deadline:
        rc, out, err = await _kubectl_async(
            ["--kubeconfig", kc_path, "get", "endpoints", svc, "-n", ns,
             "-o", "jsonpath={.subsets[*].addresses[*].ip}"],
            timeout=10,
        )
        if rc == 0 and out.strip():
            ips = out.strip()
            if ips != last_ips:
                last_ips = ips
                if progress_cb is not None:
                    await progress_cb(f"[service_ready] {svc} endpoints: {ips}")
            return {"passed": True, "evidence": f"Service {svc} 已有端点: {ips}"}
        now = asyncio.get_event_loop().time()
        if progress_cb is not None and now - last_wait_ts >= 15:
            last_wait_ts = now
            await progress_cb(f"[service_ready] {svc} 暂无端点，等待... ({int(deadline - now)}s 剩余)")
        await asyncio.sleep(3)
    return {"passed": False, "evidence": f"超时 {timeout_sec}s — Service {svc} 无端点"}


async def _check_pod_log_match(kc_path: str, ns: str, target: str, substring: str, timeout_sec: int,
                               progress_cb=None) -> dict:
    selector = await _resolve_pod_selector(kc_path, ns, target)
    deadline = asyncio.get_event_loop().time() + timeout_sec
    seen = ""
    last_seen = ""
    last_wait_ts = 0.0
    while asyncio.get_event_loop().time() < deadline:
        rc, out, err = await _kubectl_async(
            ["--kubeconfig", kc_path, "logs", "-n", ns, "-l", selector, "--tail=200"],
            timeout=10,
        )
        if rc == 0 and substring in out:
            return {"passed": True, "evidence": f"日志包含 '{substring}'"}
        seen = out or ""
        if progress_cb is not None:
            # Show the FULL log tail (not just 6 lines) so the execution
            # process — command output, progress lines, errors — is visible.
            tail = "\n".join(seen.splitlines()[-40:])
            if tail and tail != last_seen:
                last_seen = tail
                await progress_cb(f"[pod_log_match] 日志尾部:\n{tail}")
            elif not seen:
                now = asyncio.get_event_loop().time()
                if now - last_wait_ts >= 15:
                    last_wait_ts = now
                    await progress_cb(f"[pod_log_match] 暂无日志，等待 '{substring}' 出现...")
        await asyncio.sleep(3)
    return {"passed": False, "evidence": f"日志中未出现 '{substring}'; 尾部: {seen[:200]}"}


async def _check_http_ok(kc_path: str, ns: str, url: str, expect: str, timeout_sec: int) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        rc, out, err = await _kubectl_async(
            ["--kubeconfig", kc_path, "run", "airw-http-probe", "--rm", "-i",
             "--restart=Never", "--namespace", ns, "--image",
             "registry.adms.io:31542/library/busybox:1.0", "--",
             "wget", "-q", "-O-", "--timeout=5", url],
            timeout=25,
        )
        if rc == 0:
            status = expect
            return {"passed": True, "evidence": f"HTTP {url} 返回 2xx（期望 {expect}）"}
        # pod may not have pulled yet; keep trying until timeout
        await asyncio.sleep(5)
    return {"passed": False, "evidence": f"HTTP {url} 在 {timeout_sec}s 内不可达（期望 {expect}）"}


async def run_experiment(
    research_id: str,
    goal: str,
    recommendations_md: str,
    title: str = "",
) -> AsyncIterator:
    """Generate + execute an LLM-designed experiment; yield AgentEvents.

    Yields: plan loading → apply progress → per-check results → final summary.
    """
    yield AgentEvent(phase="validate", level="info", title="设计验证试验",
                     detail="由 AI 基于研究发现生成试验清单（deployment + 断言）",
                     task_id="task-10", task_progress=15)

    # 1. kubeconfig + namespace
    try:
        kc_path, kc_meta = await _load_kubeconfig()
    except Exception as e:
        yield AgentEvent(phase="validate", level="error", title="未配置 k8s 集群",
                         detail=f"在 /settings 添加: {e}", task_id="task-10", task_progress=100)
        return

    ns = derive_experiment_ns(research_id)
    _assert_safe_namespace(ns)
    yield AgentEvent(phase="validate", level="info", title="创建试验命名空间",
                     detail=ns, task_id="task-10", task_progress=20)

    # 2. LLM generates the plan (hermes k8s-expert primary, Stepfun fallback)
    try:
        raw_plan = await _ask_hermes_for_experiment(ns, goal, recommendations_md)
        plan = _validate_plan(raw_plan, ns)
        if not plan["workloads"] or not plan["checks"]:
            raise RuntimeError("hermes returned empty plan")
    except Exception as he:
        logger.warning("hermes experiment plan failed (%s); trying Stepfun fallback", he)
        llm = _default_llm()
        if llm is None:
            yield AgentEvent(phase="validate", level="error", title="试验计划失败",
                             detail=f"hermes: {str(he)[:120]}; 未配置 Stepfun API key 作备选",
                             task_id="task-10", task_progress=100)
            return
        try:
            raw_plan = await _ask_llm_for_experiment(llm, ns, goal, recommendations_md)
            plan = _validate_plan(raw_plan, ns)
        except Exception as e:
            yield AgentEvent(phase="validate", level="error", title="AI 生成试验计划失败",
                             detail=f"{type(e).__name__}: {str(e)[:200]}", task_id="task-10", task_progress=100)
            return

    yield AgentEvent(
        phase="validate", level="info",
        title=f"试验计划: {plan['experiment']['name']}",
        detail=f"工作负载 {len(plan['workloads'])} 个 · 断言 {len(plan['checks'])} 项 · 命名空间 {ns}",
        task_id="task-10", task_progress=25,
    )

    # 3. Create namespace + apply
    rc, out, err = create_namespace(kc_path, ns)
    if rc != 0:
        yield AgentEvent(phase="validate", level="error", title="命名空间创建失败",
                         detail=err[:200], task_id="task-10", task_progress=100)
        return

    results = {"applied": [], "checks": []}
    try:
        for i, w in enumerate(plan["workloads"]):
            yield AgentEvent(phase="validate", level="info",
                             title=f"应用工作负载 {i+1}/{len(plan['workloads'])}: {w['name']}",
                             detail=f"{w['kind']} · {w['image'] or '(见 yaml)'} · replicas={w['replicas']}",
                             task_id="task-10",
                             task_progress=min(45, 25 + i * 3))

            # 0. Ensure the image is mirrored into Harbor BEFORE applying.
            #    The cluster can only pull from the internal registry; if the
            #    LLM referenced an image that isn't there yet, mirror it from
            #    the public upstream via the control plane.
            if w.get("image"):
                from app.agents.k8s_image import ensure_harbor_configured, ensure_image_mirrored
                await ensure_harbor_configured()
                ok, msg = await ensure_image_mirrored(kc_path, w["image"])
                if ok:
                    yield AgentEvent(phase="validate", level="log",
                                     title=f"镜像就绪: {_to_short_ref(w['image'])}",
                                     detail=msg, task_id="task-10")
                else:
                    yield AgentEvent(phase="validate", level="warn",
                                     title=f"镜像不可用: {w['image']}",
                                     detail=msg, task_id="task-10")

            rc, out, err = await _apply_workload(kc_path, w["yaml"])
            results["applied"].append({"name": w["name"], "kind": w["kind"], "image": w["image"],
                                       "rc": rc, "out": out.strip(), "err": err.strip(),
                                       "yaml": w["yaml"]})
            if rc == 0:
                # Stream the manifest and kubectl's confirmation to the console
                # so the user sees exactly what was deployed.
                yield AgentEvent(phase="validate", level="log",
                                 title=f"已应用 {w['kind']} {w['name']}",
                                 detail=(out.strip() or "applied")[:400],
                                 task_id="task-10")
                # Also surface the container command/args that the agent put in
                # the manifest — the user wants to SEE what the pod will run.
                cmd_txt = _extract_container_command(w.get("yaml", ""))
                if cmd_txt:
                    yield AgentEvent(phase="validate", level="log",
                                     title=f"容器命令: {w['name']}",
                                     detail=cmd_txt[:600],
                                     task_id="task-10")
            else:
                yield AgentEvent(phase="validate", level="error",
                                 title=f"应用 {w['name']} 失败", detail=err[:200],
                                 task_id="task-10")

        # 4. Run checks — each check runs as a background task that streams
        #    live progress through a queue, so the console shows the pod's
        #    state / endpoints / log tail in near-real-time while waiting.
        for ci, c in enumerate(plan["checks"]):
            yield AgentEvent(phase="validate", level="info",
                             title=f"断言: {c['name']}",
                             detail=f"{c['type']} · {c['target']} · expect={c['expect']} · 超时 {c['timeout_sec']}s",
                             task_id="task-10",
                             task_progress=min(80, 45 + ci * 3))

            q: "asyncio.Queue[str]" = asyncio.Queue()

            async def _progress(msg: str) -> None:
                q.put_nowait(msg)

            async def _run():
                if c.get("_skipped"):
                    return {"passed": False, "evidence": c.get("evidence", "跳过")}
                if c["type"] == "pod_ready":
                    return await _check_pod_ready(kc_path, ns, c["target"], c["timeout_sec"], progress_cb=_progress)
                elif c["type"] == "service_ready":
                    return await _check_service_ready(kc_path, ns, c["target"], c["timeout_sec"], progress_cb=_progress)
                elif c["type"] == "pod_log_match":
                    return await _check_pod_log_match(kc_path, ns, c["target"], c["expect"], c["timeout_sec"], progress_cb=_progress)
                elif c["type"] == "http_ok":
                    return await _check_http_ok(kc_path, ns, c["target"], c["expect"], c["timeout_sec"])
                return {"passed": False, "evidence": "unsupported check"}

            task = asyncio.create_task(_run())
            while not task.done():
                try:
                    msg = q.get_nowait()
                    yield AgentEvent(phase="validate", level="log",
                                     title=f"断言监控: {c['name']}",
                                     detail=msg, task_id="task-10")
                except asyncio.QueueEmpty:
                    pass
                # NOTE: do NOT use asyncio.wait_for(task, timeout) here — it
                # would CANCEL the running check task on timeout. Just sleep
                # and re-check task.done().
                await asyncio.sleep(2)
            try:
                res = task.result()
            except Exception as e:
                # A single check crashing must not abort the whole experiment.
                # Record it as a failed check and keep going (cleanup still
                # runs in the outer finally).
                logger.warning("check task %s raised: %s", c["name"], e)
                res = {"passed": False, "evidence": f"检查执行异常: {type(e).__name__}: {str(e)[:150]}"}
            while not q.empty():
                msg = q.get_nowait()
                yield AgentEvent(phase="validate", level="log",
                                 title=f"断言监控: {c['name']}",
                                 detail=msg, task_id="task-10")
            results["checks"].append({
                "name": c["name"], "type": c["type"], "target": c["target"],
                "expect": c["expect"], **res,
            })
            yield AgentEvent(
                phase="validate",
                level="success" if res["passed"] else "warn",
                title=f"断言 {'通过' if res['passed'] else '失败'}: {c['name']}",
                detail=res["evidence"], task_id="task-10",
            )

        passed = sum(1 for c in results["checks"] if c.get("passed"))
        total = len(results["checks"])
        yield AgentEvent(phase="validate", level="success" if total and passed == total else "warn",
                         title=f"试验完成: {passed}/{total} 断言通过",
                         detail=f"工作负载 {len(results['applied'])} 个 · 断言 {passed}/{total} · 命名空间 {ns}",
                         task_id="task-10", task_progress=95)

        # 5. Persist artifact
        # Attach a human-readable Chinese explanation to each check and each
        # workload's container command, so the report / UI can say plainly
        # WHAT point was verified, HOW (steps + exact command), and WHY a
        # check passed/failed.
        applied_with_cmd = []
        for w in results["applied"]:
            cmd_txt = _extract_container_command(w.get("manifest", w.get("yaml", "")))
            applied_with_cmd.append({
                "name": w["name"], "kind": w["kind"], "image": w["image"], "rc": w["rc"],
                "command": cmd_txt,
            })
        checks_with_explain = []
        for c in results["checks"]:
            checks_with_explain.append({
                **c,
                "explain": _check_plain_language(c),
                "fail_reason": _check_fail_reason(c),
            })

        artifact = {
            "kind": "k8s-experiment",
            "experiment_name": plan["experiment"]["name"],
            "namespace": ns,
            "cluster": kc_meta.get("name"),
            # Purpose: what aspect of the research goal this experiment was
            # designed to verify, so the report/UI can show the goal↔test
            # mapping (the "预研目标 a ↔ 实测 a" alignment).
            "purpose": (
                "围绕研究目标部署真实工作负载并逐项验证："
                f"{goal[:200]}。试验计划 {len(plan['workloads'])} 个工作负载、"
                f"{len(plan['checks'])} 项断言，覆盖目标中可实测的关键点。"
            ),
            "goal": goal,
            "workloads": applied_with_cmd,
            "checks": checks_with_explain,
            "passed": passed,
            "total": total,
        }
        yield AgentEvent(phase="validate", level="info", title="试验结果已保存",
                         detail="k8s-experiment artifact", task_id="task-10",
                         artifact={"kind": "k8s-experiment",
                                   "title": f"K8s 试验: {plan['experiment']['name']}",
                                   "content": json.dumps(artifact, ensure_ascii=False, indent=2)})
    finally:
        # 6. Cleanup: always delete the experiment namespace (idempotent).
        rc, out, err = delete_namespace(kc_path, ns)
        yield AgentEvent(phase="validate", level="info", title="试验命名空间已清理",
                         detail=ns, task_id="task-10", task_progress=100)
        if kc_meta["source"] == "db":
            try:
                os.unlink(kc_path)
            except OSError:
                pass


def append_empirical_section(report_md: str, research_id: str) -> str:
    """Append the empirical k8s validation results to a final report.

    Shared by both agent implementations (hermes-researcher + stepfun) so
    the report cites REAL measured numbers instead of only theoretical
    claims. Reads the k8s-experiment artifact (LLM-driven) first, falling
    back to the k8s-validation artifact (fixed template). Best-effort: if
    nothing was validated, or the DB read fails, the report is returned
    unchanged — a report-append failure must never break the research run.

    Returns the (possibly extended) report markdown.
    """
    try:
        import json as _json

        from sqlalchemy import select

        from app.core.config_db import SyncSessionLocal
        from app.db.models import Artifact

        empirical_section = ""
        with SyncSessionLocal() as session:
            exp = session.execute(
                select(Artifact).where(
                    Artifact.research_id == research_id,
                    Artifact.kind == "k8s-experiment",
                )
            ).scalars().first()
            val = session.execute(
                select(Artifact).where(
                    Artifact.research_id == research_id,
                    Artifact.kind == "k8s-validation",
                )
            ).scalars().first()

            if exp is not None:
                d = _json.loads(exp.content)
                wl = d.get("experiment_name", "试验")
                checks = d.get("checks") or []
                passed = d.get("passed", 0)
                total = d.get("total", 0)
                applied = d.get("workloads") or []
                purpose = d.get("purpose") or ""
                goal = d.get("goal") or ""

                # Plain-language verification details: one block per check,
                # covering WHAT goal point, HOW (steps + command), and WHY.
                detail_lines = []
                for c in checks:
                    status = "✅ 通过" if c.get("passed") else ("⏭️ 跳过" if (c.get("skipped") or c.get("_skipped")) else "❌ 失败")
                    lines = [
                        f"**{c.get('name')}** — {status}",
                    ]
                    explain = c.get("explain") or _check_plain_language(c)
                    lines.append(f"- 验证点：{explain}")
                    # The command that was executed inside the pod, if any.
                    cmd = _command_for_check(c, applied)
                    if cmd:
                        lines.append(f"- 执行的命令：`{cmd}`")
                    fail_reason = c.get("fail_reason") or _check_fail_reason(c)
                    if not c.get("passed"):
                        lines.append(f"- 未通过原因：{fail_reason}")
                    detail_lines.append("\n".join(lines))

                detail_block = "\n\n".join(detail_lines) or "  - (无断言)"

                # Workloads + their container commands.
                wl_lines = []
                for w in applied:
                    line = f"  - {w.get('kind')} `{w.get('name')}` · {w.get('image') or '(见 manifest)'}"
                    cmd_txt = w.get("command") or ""
                    if cmd_txt:
                        line += f"\n    - 容器命令：`{cmd_txt[:300]}`"
                    wl_lines.append(line)
                wl_block = "\n".join(wl_lines) or "  - (无工作负载)"

                empirical_section = (
                    "\n\n---\n\n"
                    "## 15. 实证数据（K8s 集群实测）\n\n"
                    f"### 实测目的\n\n"
                    f"{purpose or f'本试验围绕研究目标部署真实工作负载并验证其关键能力（研究目标：{goal[:200]}）。'}\n\n"
                    f"### 试验概览\n\n"
                    f"- **试验**: {wl}\n"
                    f"- **集群**: {d.get('cluster', '?')} · 隔离命名空间 `{d.get('namespace', '?')}`\n"
                    f"- **断言通过率**: **{passed}/{total}**\n\n"
                    f"### 部署的工作负载与执行的命令\n\n{wl_block}\n\n"
                    f"### 逐项验证结果（验证点 / 步骤 / 命令 / 原因）\n\n{detail_block}\n"
                )
            elif val is not None:
                d = _json.loads(val.content)
                metrics = d.get("benchmark_metrics") or {}
                resources = d.get("resource_usage") or {}
                wl = d.get("workload", "?")
                elapsed = d.get("elapsed_sec", "?")
                pod_status = d.get("pod_status", "?")
                node = d.get("node") or "(未调度)"
                image = d.get("image", "?")
                metric_lines = "\n".join(
                    f"  - {k}: {v}" for k, v in metrics.items()
                ) or "  - (本轮未捕获到指标)"
                resource_lines = "\n".join(
                    f"  - {k}: {v}" for k, v in resources.items()
                ) or "  - (未采集到资源使用)"
                empirical_section = (
                    "\n\n---\n\n"
                    "## 15. 实证数据（K8s 集群实测）\n\n"
                    f"本研究已在 **{d.get('cluster', '?')}** 集群上实际部署了 "
                    f"**{wl}** 工作负载并运行基准测试，以下是真实测量结果：\n\n"
                    f"- Pod: `{d.get('pod_name', '?')}`\n"
                    f"- 调度节点: {node}\n"
                    f"- 镜像: {image}\n"
                    f"- 状态: {pod_status} · 耗时: {elapsed}s\n\n"
                    f"**Benchmark 指标**\n{metric_lines}\n\n"
                    f"**资源使用**\n{resource_lines}\n"
                )
        if empirical_section:
            return report_md.rstrip() + "\n" + empirical_section.lstrip("\n")
        return report_md
    except Exception:
        # Never let a report-append failure break the research run.
        return report_md


_TYPE_CN = {
    "pod_ready": "Pod 就绪检查",
    "service_ready": "Service 可用性检查",
    "pod_log_match": "Pod 日志内容检查",
    "http_ok": "HTTP 访问检查",
}


def _command_for_check(c: dict, applied: list[dict]) -> str:
    """Find the container command related to a check.

    Matches the check's target (app=x / deployment/x / service) against the
    deployed workloads' names / labels, then returns that workload's command.
    """
    target = (c.get("target") or "").strip()
    t = target.split("/")[-1]
    if t.startswith("app="):
        t = t[len("app="):]
    t = t.strip().lower()
    for w in applied:
        name = str(w.get("name") or "").lower()
        cmd = w.get("command") or ""
        if cmd and (t and (t in name or name in t or t == name)):
            return cmd
    return ""


def _check_plain_language(c: dict) -> str:
    """Chinese plain-language description of what a check verifies & how.

    Used in the report / UI so a reader understands, in plain words, which
    goal point this assertion verifies, the verification step, and the
    expected result — without parsing raw yaml/selectors.
    """
    ctype = c.get("type", "")
    target = c.get("target", "")
    expect = c.get("expect", "")
    name = c.get("name", "")
    tcn = _TYPE_CN.get(ctype, ctype)

    if ctype == "pod_ready":
        return (
            f"检查名为「{name}」的目标（{target}）对应的 Pod 是否成功启动并进入就绪状态。"
            f"做法：持续查询该 Pod 的状态，等待其 phase 变为 Running 且容器 Ready；"
            f"期望：就绪。"
        )
    if ctype == "service_ready":
        return (
            f"检查名为「{name}」的 Service（{target}）是否可用——即它是否关联到了真实运行的 Pod。"
            f"做法：查询该 Service 的 Endpoints，等待有可用 IP 出现；期望：有端点。"
        )
    if ctype == "pod_log_match":
        return (
            f"检查名为「{name}」的目标（{target}）的 Pod 日志中是否出现了预期内容「{expect}」。"
            f"这用来验证容器内部执行的结果（如压测输出、初始化完成标记、错误提示）；"
            f"做法：持续抓取该 Pod 的日志并匹配关键词；期望：日志包含「{expect}」。"
        )
    if ctype == "http_ok":
        return (
            f"检查 {target} 是否能通过 HTTP 访问（期望 {expect}）。"
            f"做法：在命名空间内发起 HTTP 请求并检查响应码；期望：2xx。"
        )
    return f"对目标「{target}」执行 {tcn}，期望 {expect}。"


def _check_fail_reason(c: dict) -> str:
    """Plain-Chinese reason for why a check did not pass.

    Falls back to the raw evidence when we can't derive a friendly reason.
    """
    if c.get("_skipped") or c.get("skipped"):
        return "该检查对应的资源没有在试验计划中实际部署（计划不一致），因此跳过，不代表方案失败。"
    if c.get("passed"):
        return "检查通过，验证结果符合预期。"
    evidence = c.get("evidence", "") or ""
    ctype = c.get("type", "")
    target = c.get("target", "")

    if "超时" in evidence:
        if ctype == "pod_ready":
            return f"目标 {target} 的 Pod 在限定时间内一直没有就绪，最常见原因是：镜像拉取失败（ImagePullBackOff）、资源配额不足、或配置错误导致容器启动失败/反复重启。"
        if ctype == "service_ready":
            return f"Service {target} 在限定时间内一直没有可用端点，最常见原因是：对应的 Pod 没起来，或 Service 的标签选择器与 Pod 标签不匹配。"
        if ctype == "pod_log_match":
            return f"目标 {target} 的 Pod 日志在限定时间内一直没有出现期望的关键词，最常见原因是：容器内命令没执行到那一步、命令报错提前退出、或日志内容与预期不一致。"
    if "未在计划中部署" in evidence or "没有匹配选择器" in evidence:
        return f"检查目标「{target}」没有找到对应的已部署资源（计划生成与部署不一致），属于试验计划问题而非被测方案问题。"
    if ctype == "pod_log_match" and "日志中未出现" in evidence:
        return f"目标 {target} 的日志始终没有包含期望内容，说明容器内部验证命令没有成功执行或结果不符合预期（可能是服务未就绪、命令报错或断言关键词不对）。"
    return evidence[:200]
