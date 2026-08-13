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


def _default_llm() -> StepfunClient | None:
    """Build a StepfunClient from settings if an API key is configured."""
    try:
        from app.core.config import settings
        if not settings.stepfun_api_key:
            return None
        return StepfunClient(
            api_key=settings.stepfun_api_key,
            base_url=settings.stepfun_base_url or "https://api.stepfun.com/step_plan/v1",
            model=settings.stepfun_model or "step-3.7-flash",
            timeout=90.0,
        )
    except Exception:
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
        "为这项研究设计可执行的K8s验证试验：\n\n"
        "目标：\n" + (goal or "")[:800] + "\n\n"
        "推荐方案：\n" + (recommendations_md or "")[:3000] + "\n\n"
        "要求：\n"
        f"1. 命名空间必须用 {namespace}。\n"
        "2. 镜像只能用 registry.adms.io:31542/library/<image>:<tag>（redis:7.0.4/postgres:15/"
        "mysql:8.0/mongo:8.0/nginx:1.26.2-alpine/busybox:1.0）。\n"
        "3. Deployment 不要写 restartPolicy；labels 用 app=<名>；checks target 用 app=<名>。\n"
        "4. 压测容器命令必须先 until 等待依赖就绪再压测，输出含 'requests per second' 或 'ops'。"
        "等待命令写法示例：until redis-cli -h redis-cache ping 2>/dev/null | grep -q PONG; do sleep 1; done"
        "（redis-cli 没有 -t 参数，不要用 redis-cli -t）。\n"
        "5. 使用 mysql 镜像时，容器必须设置 MYSQL_ROOT_PASSWORD（或 MYSQL_ALLOW_EMPTY_PASSWORD=yes），"
        "否则 mysql 8 容器无法完成初始化；mysql 默认数据目录是 /var/lib/mysql。\n"
        "5. 资源请求 cpu<=500m, memory<=512Mi。\n"
        "6. 一个 workload 的 yaml 只放一个资源（多资源就放多个 workload 条目）。\n\n"
        "JSON格式：\n"
        "{\"experiment\":{\"name\":\"x\",\"namespace\":\"" + namespace + "\"},"
        "\"workloads\":[{\"name\":\"x\",\"kind\":\"Deployment\",\"image\":\"registry.adms.io:31542/library/redis:7.0.4\",\"replicas\":1,\"yaml\":\"...\"}],"
        "\"checks\":[{\"name\":\"c\",\"type\":\"pod_ready|service_ready|pod_log_match|http_ok\",\"target\":\"app=x\",\"expect\":\"true\",\"timeout_sec\":90}]}"
    )

    cmd = [hermes_bin, "chat", "-q", prompt, "--cli",
           "--max-turns", "3", "--yolo", "-p", profile, "-s", skills]
    logger.info("Running hermes k8s-expert for experiment plan ...")
    proc = await _asyncio.create_subprocess_exec(
        *cmd,
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

    cleaned_checks = []
    for c in checks:
        if not isinstance(c, dict):
            continue
        ctype = str(c.get("type", ""))
        if ctype not in ALLOWED_CHECK_TYPES:
            logger.warning("skipping unsupported check type: %s", ctype)
            continue
        cleaned_checks.append({
            "name": str(c.get("name", ctype))[:80],
            "type": ctype,
            "target": str(c.get("target", ""))[:200],
            "expect": str(c.get("expect", ""))[:200],
            "timeout_sec": max(10, int(c.get("timeout_sec") or 90)),
        })

    return {
        "experiment": {
            "name": str(experiment.get("name", "experiment"))[:80],
            "namespace": namespace,
        },
        "workloads": cleaned_workloads,
        "checks": cleaned_checks,
    }


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


async def _check_pod_ready(kc_path: str, ns: str, target: str, timeout_sec: int) -> dict:
    """Wait until a pod matching target (selector or deployment/name) is Ready."""
    selector = await _resolve_pod_selector(kc_path, ns, target)
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        rc, out, err = await _kubectl_async(
            ["--kubeconfig", kc_path, "get", "pod", "-n", ns,
             "-l", selector, "-o", "jsonpath={.items[*].status.conditions[?(@.type==\"Ready\")].status}"],
            timeout=10,
        )
        if rc == 0 and out.strip() and "True" in out:
            return {"passed": True, "evidence": f"pod ready ({target}): {out.strip()}"}
        await asyncio.sleep(3)
    return {"passed": False, "evidence": f"timeout after {timeout_sec}s waiting pod ready ({target})"}


async def _check_service_ready(kc_path: str, ns: str, service: str, timeout_sec: int) -> dict:
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
            return {"passed": False, "evidence": f"no service matches selector '{service}'"}
    svc = svc.split("/")[-1]
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        rc, out, err = await _kubectl_async(
            ["--kubeconfig", kc_path, "get", "endpoints", svc, "-n", ns,
             "-o", "jsonpath={.subsets[*].addresses[*].ip}"],
            timeout=10,
        )
        if rc == 0 and out.strip():
            return {"passed": True, "evidence": f"service {svc} has endpoints: {out.strip()}"}
        await asyncio.sleep(3)
    return {"passed": False, "evidence": f"timeout after {timeout_sec}s — service {svc} no endpoints"}


async def _check_pod_log_match(kc_path: str, ns: str, target: str, substring: str, timeout_sec: int) -> dict:
    selector = await _resolve_pod_selector(kc_path, ns, target)
    deadline = asyncio.get_event_loop().time() + timeout_sec
    seen = ""
    while asyncio.get_event_loop().time() < deadline:
        rc, out, err = await _kubectl_async(
            ["--kubeconfig", kc_path, "logs", "-n", ns, "-l", selector, "--tail=200"],
            timeout=10,
        )
        if rc == 0 and substring in out:
            return {"passed": True, "evidence": f"log contains '{substring}'"}
        seen = out or ""
        await asyncio.sleep(3)
    return {"passed": False, "evidence": f"log never contained '{substring}'; tail: {seen[:200]}"}


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
            return {"passed": True, "evidence": f"http {url} -> 2xx (expect {status})"}
        # pod may not have pulled yet; keep trying until timeout
        await asyncio.sleep(5)
    return {"passed": False, "evidence": f"http {url} not reachable within {timeout_sec}s (expect {expect})"}


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
            rc, out, err = await _apply_workload(kc_path, w["yaml"])
            results["applied"].append({"name": w["name"], "kind": w["kind"], "image": w["image"],
                                       "rc": rc, "out": out.strip(), "err": err.strip()})
            if rc != 0:
                yield AgentEvent(phase="validate", level="error",
                                 title=f"应用 {w['name']} 失败", detail=err[:200],
                                 task_id="task-10")

        # 4. Run checks
        for c in plan["checks"]:
            yield AgentEvent(phase="validate", level="info",
                             title=f"断言: {c['name']}",
                             detail=f"{c['type']} · {c['target']} · expect={c['expect']} · 超时 {c['timeout_sec']}s",
                             task_id="task-10",
                             task_progress=min(80, 45 + plan["checks"].index(c) * 3))
            res = None
            if c["type"] == "pod_ready":
                res = await _check_pod_ready(kc_path, ns, c["target"], c["timeout_sec"])
            elif c["type"] == "service_ready":
                res = await _check_service_ready(kc_path, ns, c["target"], c["timeout_sec"])
            elif c["type"] == "pod_log_match":
                res = await _check_pod_log_match(kc_path, ns, c["target"], c["expect"], c["timeout_sec"])
            elif c["type"] == "http_ok":
                res = await _check_http_ok(kc_path, ns, c["target"], c["expect"], c["timeout_sec"])
            if res is None:
                res = {"passed": False, "evidence": "unsupported check"}
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
        artifact = {
            "kind": "k8s-experiment",
            "experiment_name": plan["experiment"]["name"],
            "namespace": ns,
            "cluster": kc_meta.get("name"),
            "workloads": [{"name": w["name"], "kind": w["kind"], "image": w["image"], "rc": w["rc"]}
                          for w in results["applied"]],
            "checks": results["checks"],
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
                check_lines = "\n".join(
                    f"  - {'✅' if c.get('passed') else '❌'} {c.get('name')} "
                    f"[{c.get('type')} → {c.get('target')}] "
                    f"expect={c.get('expect')}: {c.get('evidence', '')[:120]}"
                    for c in checks
                ) or "  - (无断言)"
                wl_lines = "\n".join(
                    f"  - {w.get('kind')} `{w.get('name')}` · {w.get('image') or '(见 manifest)'}"
                    for w in applied
                ) or "  - (无工作负载)"
                empirical_section = (
                    "\n\n---\n\n"
                    "## 15. 实证数据（K8s 集群实测）\n\n"
                    f"本研究已在 **{d.get('cluster', '?')}** 集群的隔离命名空间 "
                    f"**`{d.get('namespace', '?')}`** 中，按 AI 生成的试验计划部署了以下工作负载并逐项断言：\n\n"
                    f"**试验**: {wl} · **断言通过率**: {passed}/{total}\n\n"
                    f"**部署的工作负载**\n{wl_lines}\n\n"
                    f"**验证断言结果**\n{check_lines}\n"
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
