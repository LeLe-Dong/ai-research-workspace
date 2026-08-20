"""Decision helpers for the research pipeline.

`should_run_k8s_validation` decides whether the optional k8s cluster
validation phase should fire. Uses a multi-signal approach so the system
can pick up "this research benefits from a real cluster test" even when
the keyword is in the user's goal/title (before the LLM runs) rather than
only in the LLM's output.

3-state trigger:
    0  = auto  — decide from goal/title/constraints + LLM output + depth
    1  = on    — always run
   -1  = off   — always skip
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Research


# ── Keyword registry ─────────────────────────────────────────────
# Tiered by signal strength. Strong keywords alone are decisive.
# Medium keywords are decisive when 2+ appear. Weak keywords reinforce
# but never trigger alone.

K8S_KEYWORDS_STRONG = (
    "kubernetes", "k8s", "kubectl", "helm chart", "kustomize",
    "istio", "linkerd", "argo rollouts", "operator",
    "rancher", "openshift", "eks ", "gke ", "aks ",
)

K8S_KEYWORDS_MEDIUM = (
    "pod", "pods", "deployment strategy", "rolling update",
    "service mesh", "namespace", "helm", "daemonset",
    "statefulset", "configmap", "secret ",
)

K8S_KEYWORDS_WEAK = (
    "容器", "容器化", "container", "containerd",
    "cluster", "集群", "节点", "node ", "镜像", "镜像构建",
    "deploy", "deployment ", "rollout", "scaling",
    "k8s",  # also a strong keyword but counted in weak bucket for fallback
)


@dataclass(frozen=True)
class K8sDecision:
    should_run: bool
    reason: str           # human-readable explanation (logged + shown in timeline)
    input_score: int
    output_score: int


def _score(text: str) -> int:
    """Tier-weighted keyword score in [0, 3]."""
    if not text:
        return 0
    lo = text.lower()
    score = 0
    if any(kw in lo for kw in K8S_KEYWORDS_STRONG):
        score += 2
    medium_hits = sum(1 for kw in K8S_KEYWORDS_MEDIUM if kw in lo)
    if medium_hits >= 2:
        score += 1
    elif medium_hits == 1 and score == 0:
        # Single medium hit alone is borderline; only count if no strong
        score += 0  # keep at 0; rely on output side
    weak_hits = sum(1 for kw in K8S_KEYWORDS_WEAK if kw in lo)
    if weak_hits >= 3:
        score += 1
    return min(score, 3)


def should_run_k8s_validation(
    research: Research,
    llm_output: str = "",
) -> K8sDecision:
    """Decide whether to deploy a test pod in the cluster for this research.

    Args:
        research: The Research row (provides title/goal/constraints/depth
                  + the user-set requires_k8s_validation flag).
        llm_output: Final cleaned output of the LLM (may be empty if not
                    yet generated — e.g. for the pre-flight check).

    Returns:
        K8sDecision with should_run, reason, and scores for observability.
    """
    flag = research.requires_k8s_validation or 0

    # ── Explicit overrides ──
    if flag == 1:
        return K8sDecision(True, "用户强制开启", 0, 0)
    if flag == -1:
        return K8sDecision(False, "用户强制关闭", 0, 0)

    # ── Auto: multi-signal ──
    input_text = " ".join([
        research.title or "",
        research.goal or "",
        research.constraints or "",
    ])
    input_score = _score(input_text)
    output_score = _score(llm_output or "")

    # Quick depth almost never benefits from a real cluster test.
    if research.depth == "quick" and input_score < 2:
        return K8sDecision(
            False,
            f"depth=quick 且输入侧信号弱 (input={input_score})",
            input_score, output_score,
        )

    # Strong evidence on either side triggers.
    if input_score >= 2 or output_score >= 2:
        return K8sDecision(
            True,
            f"自动触发 (input={input_score}, output={output_score})",
            input_score, output_score,
        )

    # Single medium signal on the input + at least one weak on output: borderline yes
    if input_score >= 1 and output_score >= 1:
        return K8sDecision(
            True,
            f"中等信号触发 (input={input_score}, output={output_score})",
            input_score, output_score,
        )

    return K8sDecision(
        False,
        f"无明确 K8s 信号 (input={input_score}, output={output_score})",
        input_score, output_score,
    )