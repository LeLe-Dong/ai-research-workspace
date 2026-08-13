"""Generate a complete research plan from a one-line subject.

The user (who often doesn't know what a "good" research spec looks like)
types a single sentence — e.g. "评估 Redis 集群高可用方案" — and we produce
a ready-to-submit plan: title, goal, constraints, expected_output, depth,
priority, k8s validation hint.

Generation runs through the LOCAL hermes CLI (no dependence on the Stepfun
API quota, which has been exhausted). We request strict JSON and sanitize it
in the same way as the k8s experiment planner.

Fallbacks (in order):
  1. hermes chat (local) — primary
  2. Stepfun chat_json if a key is configured
  3. heuristic template (works offline, no LLM at all)
"""
from __future__ import annotations

import asyncio
import json
import logging

from app.agents.llm import StepfunClient

logger = logging.getLogger(__name__)

PLAN_SYSTEM = """你是资深研究顾问。用户只给出一句话研究主题，你需要把它扩展成一份可直接执行的研究方案。

只输出一个 JSON 对象，不要任何解释、markdown 代码块或前后缀。

JSON schema（字段名不能改）：
{
  "title": str,                 # 简洁标题（≤40字）
  "goal": str,                  # 详细研究目标：背景、要解决的问题、研究角度（300-500字）
  "constraints": str,           # 约束条件：技术栈、资源、范围限制
  "expected_output": str,       # 预期产出：报告结构/对比表/推荐方案等
  "depth": "quick" | "standard" | "deep",
  "priority": "low" | "medium" | "high",
  "requires_k8s_validation": int   # 0=自动, 1=强制集群验证, -1=不验证
}

要求：
- 保留用户核心意图，不改变主题方向
- goal 具体可执行，拆解 3-5 个分析维度
- 若主题涉及集群/部署/性能验证，requires_k8s_validation 设为 1，否则 0
- 中文输出
"""


def _fallback_plan(subject: str) -> dict:
    """Offline heuristic plan (no LLM). Keeps things usable if both paths fail."""
    subject = (subject or "").strip()
    low = subject.lower()
    k8s_hint = any(k in low for k in ("k8s", "kubernetes", "集群", "部署", "高可用", "性能"))
    return {
        "title": subject[:40] or "未命名研究",
        "goal": (
            f"针对「{subject}」进行系统性的预研分析。\n\n"
            "研究角度：\n"
            "1. 方案背景与现状：梳理相关技术背景、主流方案与适用场景。\n"
            "2. 方案对比：从功能、性能、成本、可维护性等维度对比候选方案。\n"
            "3. 关键权衡：识别关键取舍点与适用边界。\n"
            "4. 落地建议：给出明确的推荐方案与实施路径。"
        ),
        "constraints": "不涉及具体业务数据；以公开资料与技术文档为主。",
        "expected_output": "结构化预研报告，含方案对比表与推荐结论。",
        "depth": "standard",
        "priority": "medium",
        "requires_k8s_validation": 1 if k8s_hint else 0,
    }


async def _ask_hermes(subject: str) -> dict:
    import base64
    hermes_bin = "/root/.local/bin/hermes"
    prompt = (
        "你是资深研究顾问。下面是一句话研究主题：\n\n"
        + subject + "\n\n"
        "把它扩展成完整研究方案，只输出JSON（schema如下），不要解释：\n"
        '{"title":"...","goal":"...","constraints":"...","expected_output":"...",'
        '"depth":"quick|standard|deep","priority":"low|medium|high",'
        '"requires_k8s_validation":0|1|-1}'
    )
    proc = await asyncio.create_subprocess_exec(
        hermes_bin, "chat", "-q", prompt, "--cli",
        "--max-turns", "2", "--yolo", "-p", "researcher", "-s", "",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, _err = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("hermes plan generation timed out")
    text = out_b.decode("utf-8", errors="replace")
    # Strip box decorations, then extract JSON.
    try:
        from app.agents.hermes_researcher import _strip_hermes_decorations
        cleaned = _strip_hermes_decorations(text)
    except Exception:
        cleaned = text
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first < 0 or last <= first:
        raise RuntimeError("hermes did not return JSON")
    plan = json.loads(cleaned[first:last + 1])
    if not isinstance(plan, dict):
        raise RuntimeError("plan is not an object")
    return plan


def _sanitize(plan: dict, subject: str) -> dict:
    goal = str(plan.get("goal") or "").strip()
    title = str(plan.get("title") or "").strip() or subject[:40]
    if not goal:
        return _fallback_plan(subject)
    depth = plan.get("depth") if plan.get("depth") in ("quick", "standard", "deep") else "standard"
    priority = plan.get("priority") if plan.get("priority") in ("low", "medium", "high") else "medium"
    try:
        k8s = int(plan.get("requires_k8s_validation", 0))
        k8s = -1 if k8s < 0 else 1 if k8s > 0 else 0
    except (TypeError, ValueError):
        k8s = 0
    return {
        "title": title[:200],
        "goal": goal,
        "constraints": str(plan.get("constraints") or "").strip(),
        "expected_output": str(plan.get("expected_output") or "").strip(),
        "depth": depth,
        "priority": priority,
        "requires_k8s_validation": k8s,
    }


async def generate_plan(subject: str, use_llm: bool = True) -> dict:
    """Generate a complete research plan from a one-line subject.

    Returns a dict matching ResearchCreate fields (title/goal/constraints/
    expected_output/depth/priority/requires_k8s_validation).
    """
    subject = (subject or "").strip()
    if use_llm:
        # 1. local hermes
        try:
            plan = await _ask_hermes(subject)
            return _sanitize(plan, subject)
        except Exception as e:
            logger.warning("hermes plan generation failed: %s", e)
        # 2. Stepfun (if configured)
        try:
            from app.core.config import settings
            if settings.stepfun_api_key:
                llm = StepfunClient(
                    api_key=settings.stepfun_api_key,
                    base_url=settings.stepfun_base_url or "https://api.stepfun.com/step_plan/v1",
                    model=settings.stepfun_model or "step-3.7-flash",
                    timeout=60.0,
                )
                plan = await llm.chat_json(PLAN_SYSTEM, f"主题：{subject}", max_tokens=3000, temperature=0.3)
                return _sanitize(plan, subject)
        except Exception as e:
            logger.warning("Stepfun plan generation failed: %s", e)
    # 3. offline fallback
    return _fallback_plan(subject)
