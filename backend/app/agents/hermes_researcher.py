"""HermesResearcherAgent: shell out to `hermes chat --cli` to do research.

Uses Hermes Agent's own model chain (primary stepfun, fallback minimax-cn)
+ optionally loads hermes skills like `arxiv` to actually fetch sources.

Why hermes:
- Self-contained: no separate LLM API key needed (uses hermes credential pool)
- Tool-using: arxiv/blogwatcher/knowledge-base-audit available
- Quality: minimax-cn/MiniMax-M3 (your default fallback) is a strong model

Trade-offs vs StepfunAgentClient:
- Not streaming (have to wait for hermes to finish)
- Slower per call (hermes agent loop is multiple turns)
- Output format needs cleanup (hermes wraps in box UI)
"""
import asyncio
import logging
import os
import re
import shlex
import time

from app.agents.base import AgentClient, AgentEvent, ResearchRequest
from app.agents.mock import TASK_TREE, MERMAID_TEMPLATE
from app.services.decision import should_run_k8s_validation


def _req_as_research(req: ResearchRequest):
    """Adapt ResearchRequest dataclass to the duck-typed shape the decision
    helper expects (title/goal/constraints/depth/requires_k8s_validation).
    Avoids loading the Research row just for one decision.
    """
    class _R:
        pass
    r = _R()
    r.title = req.title
    r.goal = req.goal
    r.constraints = req.constraints
    r.depth = req.depth
    r.requires_k8s_validation = req.requires_k8s_validation
    return r

logger = logging.getLogger(__name__)

# Reuse task-tree from mock for UI consistency
TASK_TREE_HERMES = TASK_TREE  # same shape


# Output cleanup: strip the `╭─ ⚕ Hermes ─╮` decorative box.
# The actual content lives between the box border and the closing `╰─...─╯`.
HERMES_BOX_RE = re.compile(
    r"╭─[^\n]*?╮\s*\n(.*?)\s*╰─[^\n]*?╯",
    re.DOTALL,
)

# Process-noise lines that appear inside hermes' stdout but are NOT part of
# the final answer. Anything matching one of these gets dropped wholesale.
_HERMES_NOISE_PATTERNS = [
    re.compile(r"^\s*┌─[^─]*[─]+[^─]*[─]+"),  # ┌─ Reasoning ─…┐
    re.compile(r"^\s*└─[^─]*[─]+"),            # └─ … ─┘
    re.compile(r"^\s*┊\s*(💻|📖|🔎|✍️|✏️|💭)"),   # tool-call prefixes
    re.compile(r"^\s*┊\s*\$"),                 # command-line prompts
    re.compile(r"^\s*│"),                     # vertical box-drawing
    re.compile(r"^\s*╭─"),                    # box top
    re.compile(r"^\s*╰─"),                    # box bottom
    re.compile(r"^─{5,}"),                   # horizontal rules (─────)
    re.compile(r"^\[write_file\]"),          # tool meta headers
    re.compile(r"^\[read_file\]"),
    re.compile(r"^\[search_files\]"),
    re.compile(r"^\[terminal\]"),
    re.compile(r"^\[tool\]"),
    re.compile(r"^\[reasoning\]"),
    re.compile(r"^\s*Reviewing diff\.\.\."),  # write_file review
    re.compile(r"^\s*Review diff"),
    re.compile(r"^\s*a/.*→.*b/"),            # diff a→b paths
    re.compile(r"^\s*⚠️?\s*Iteration budget"),
    re.compile(r"^\s*⚠️?\s*Reached maximum"),
    re.compile(r"^\s*⚠\s*"),
    re.compile(r"^\s*hermes --resume"),
]


def _is_noise_line(line: str) -> bool:
    """Return True if a line is LLM process noise (thinking/tool_use/system
    status) and should be dropped from the final report."""
    for pat in _HERMES_NOISE_PATTERNS:
        if pat.match(line):
            return True
    # Also drop lines that are PURELY a thinking block indicator
    if line.strip() in {"Reasoning", "Reasoning:", "Planning"}:
        return True
    return False


def _strip_hermes_decorations(text: str) -> str:
    """Extract the inner content of hermes' final answer box.

    Hermes output typically has multiple boxes (preamble reasoning, intermediate
    status updates, and a final answer). We extract the LAST box which is the
    actual final answer to the user query.

    If the well-formed box match fails, we fall back to a two-pass filter:
      1. drop any line matching _is_noise_line (thinking, tool_use, system)
      2. drop the duplicated prompt echo at the start ("## 研究输入", "## 报告
         输出要求", "## 输出规则", "## 工具使用", "## 过程要求" sections)
    """
    # Strip ANSI escape codes
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    # Find ALL boxes; take the LAST one (final answer)
    all_boxes = HERMES_BOX_RE.findall(text)
    if all_boxes:
        return all_boxes[-1].strip()
    # Fallback: drop noise lines + prompt-echo, then return
    lines = text.split("\n")
    out = []
    for line in lines:
        if _is_noise_line(line):
            continue
        if (line.startswith("Resume this session") or line.startswith("Session:") or
                line.startswith("Duration:") or line.startswith("Messages:") or
                line.startswith("Initializing agent") or line.startswith("Query:") or
                line.startswith("─────")):
            continue
        if line.startswith("╭─") or line.startswith("╰─") or line.startswith("│ "):
            continue
        if line.strip():
            out.append(line)
    return "\n".join(out).strip()


def _extract_custom_sections(custom_block: str) -> list[str]:
    """Pull the ordered list of section names out of a rendered style block.

    `render_style_block()` produces a block like:

        ## 个性化研究维度（用户上传预研文档总结）
        ...
        **章节顺序**：
        1. **产品/方案定位**
        2. **技术架构**
        ...

    We parse the numbered list, strip the `**` markdown emphasis, and
    return the ordered section titles.
    """
    if not custom_block:
        return []
    import re as _re
    m = _re.search(r"\*\*章节顺序\*\*\s*[:：]?\s*(.+?)(?:\n\n|\Z)", custom_block, _re.DOTALL)
    blob = m.group(1) if m else custom_block
    out: list[str] = []
    for line in blob.splitlines():
        line = line.strip()
        m2 = _re.match(r"^\d+[\.、]\s*\*?\*?(.+?)\*?\*?$", line)
        if m2:
            name = m2.group(1).strip()
            if name and name not in out:
                out.append(name)
    return out


class HermesResearcherAgent(AgentClient):
    """Run a research request through `hermes chat --cli` as a background subprocess."""

    def __init__(
        self,
        hermes_bin: str = "/root/.local/bin/hermes",
        profile: str = "researcher",  # The pre-research expert profile (14-dim framework)
        skills: str = "feeds,arxiv",  # feeds for current info, arxiv for academic lookups
        timeout_seconds: int = 300,
    ):
        self.hermes_bin = hermes_bin
        self.profile = profile
        self.skills = skills
        self.timeout_seconds = timeout_seconds

    async def run_research(self, req: ResearchRequest) -> AsyncIterator[AgentEvent]:
        from typing import AsyncIterator

        # Emit task tree first for UI consistency with other agents
        for idx, (phase, name, desc) in enumerate(TASK_TREE_HERMES):
            yield AgentEvent(
                phase=phase, level="info",
                title=f"Task {idx + 1}/{len(TASK_TREE_HERMES)}: {name}",
                detail=desc,
                task_id=f"task-{idx:02d}", task_progress=0,
            )

        # Build the research prompt for hermes (sync fallback if event loop closed)
        try:
            prompt = await self._build_prompt_async(req)
        except RuntimeError:
            prompt = self._build_prompt(req)

        yield AgentEvent(
            phase="understand", level="info",
            title="Dispatching to Hermes Agent",
            detail=f"Using hermes profile={self.profile}, skills={self.skills}",
            task_id="task-00", task_progress=20,
        )

        # ── Real-time SSE streaming ──────────────────────────────────────
        # Use asyncio.Queue so the on_log callback (running inside the
        # subprocess drain) can push events to the main generator as they
        # arrive. The main generator pulls from the queue, yielding each
        # event to the executor → DB → SSE → frontend in real time.
        event_queue: asyncio.Queue = asyncio.Queue()

        # Track which task each log line belongs to, based on content cues.
        # This lets the Console group session output per task.
        def _classify_task(line: str) -> str:
            """Map a hermes output line to its owning task index.

            Heuristic — no explicit phase marker in hermes\' CLI output. We
            match common tool/keyword signatures:
              arxiv / search / url / http / fetch → research (task-01)
              compare / matrix / tradeoff         → comparison (task-04)
              score / risk / feasibility / evaluate → evaluation (task-06)
              write / report / summarize          → report (task-08)
              everything else (reasoning, system) → task-00 (requirement)
            """
            lo = line.lower()
            if any(kw in lo for kw in ("arxiv", "feeds ", "http://", "https://", "fetch", "scrape", "search ")):
                return "task-01"
            if any(kw in lo for kw in ("compare", "matrix", "tradeoff", "trade-off", "weigh")):
                return "task-04"
            if any(kw in lo for kw in ("score", "risk", "feasibility", "evaluat", "likelihood")):
                return "task-06"
            if any(kw in lo for kw in ("write", "report", "summariz", "compose", "draft")):
                return "task-08"
            return "task-00"

        async def _on_log(line: str, kind: str):
            """Called from inside the subprocess drain for every line.

            Categorize → build AgentEvent → push to queue. The main generator
            pulls and yields them in real-time so SSE delivers them as they
            arrive rather than buffering until hermes exits.
            """
            stripped = line.lstrip()
            level = "info"
            title = line[:80]
            if "Reasoning" in stripped or stripped.startswith("→"):
                ev_phase = "reasoning"
                title = "[推理] " + (stripped.split("─")[-1].strip() if "─" in stripped else stripped)[:60]
            elif any(stripped.startswith(e) for e in ("\U0001f4da ", "\U0001f4bb ", "\U0001f4d6 ", "┊ ", "\U0001f50e")):
                ev_phase = "tool"
                if "preparing" in stripped:
                    title = "[准备] " + stripped.split("preparing")[-1].strip(" …")
                elif " $ " in stripped or stripped.startswith("$"):
                    title = "[执行] " + stripped.replace("┊ ", "").strip()[:80]
                else:
                    title = "[工具] " + stripped.replace("┊ ", "").strip()[:80]
            elif "Error" in stripped or "Exception" in stripped or kind == "err":
                ev_phase = "stderr"
                level = "warn" if kind == "err" else "info"
            elif "Resume this session" in stripped or stripped.startswith("Session"):
                ev_phase = "meta"
                title = "[结束] " + stripped[:60]
            else:
                ev_phase = "log"

            # Bind to owning task so the Console groups session output per task.
            task_id = _classify_task(line)
            await event_queue.put(AgentEvent(
                phase=ev_phase, level=level, title=title,
                detail=line[:2000],
                task_id=task_id,
            ))

        async def _runner() -> str:
            """Run hermes in background; signal completion via None sentinel."""
            try:
                return await self._run_hermes_async(prompt, on_log=_on_log)
            except Exception:
                logger.exception("hermes runner crashed")
                return ""
            finally:
                # Sentinel: tell the main generator to stop pulling.
                await event_queue.put(None)

        runner_task = asyncio.create_task(_runner())

        # Drain events from the queue in real-time, yielding each to the
        # executor. This is what enables SSE real-time streaming.
        while True:
            ev = await event_queue.get()
            if ev is None:
                break
            yield ev

        raw_output = await runner_task

        if not raw_output.strip():
            raw_output = self._fallback_output(req, "timeout_or_empty")

        # Clean output
        clean = _strip_hermes_decorations(raw_output)

        # Emit the full session content as a single collapsible event. This is
        # what the user sees when they expand a task\'s log in the Console.
        yield AgentEvent(
            phase="summarize", level="success",
            title="Hermes 会话内容",
            detail=(
                f"## Hermes 完整会话输出 ({len(clean)} 字符)\n\n"
                f"profile: {self.profile}  |  skills: {self.skills}\n"
                f"raw_output: {len(raw_output)} 字符 (含 UI 装饰)\n"
                f"cleaned:   {len(clean)} 字符\n\n"
                f"---\n\n{clean[:8000]}"
                + ("\n\n... [已截断，完整内容见 final-report.md artifact]" if len(clean) > 8000 else "")
            ),
            task_id="task-00",
        )

        # Phase 4.5: K8S ENVIRONMENT VALIDATION (mid-research, immediately
        # after the LLM returns its findings — *before* we normalize /
        # summarise into the final report). The k8s-expert profile in
        # hermes-agent actually applies the test pod / deployment to the
        # real cluster and reports live status back via the validate phase
        # SSE stream. Doing this while the LLM context is still hot means
        # the report can later cite live cluster evidence.
        yield AgentEvent(
            phase="validate", level="info",
            title="环境验证",
            detail="调研结果已就绪，开始实际 K8s 环境验证",
            task_id="task-10", task_progress=0,
        )
        try:
            from app.agents.k8s import validate_with_k8s
            from app.agents.k8s_experiment import run_experiment
            # Multi-signal decision: explicit user override, input-side
            # keywords (title/goal/constraints), output-side keywords (what the
            # LLM actually produced), and depth. See services/decision.py.
            k8s_decision = should_run_k8s_validation(
                _req_as_research(req), clean
            )
            yield AgentEvent(
                phase="validate", level="info",
                title=f"环境验证 决策: {'执行' if k8s_decision.should_run else '跳过'}",
                detail=f"判定: {k8s_decision.reason}",
                task_id="task-10", task_progress=2,
            )
            if k8s_decision.should_run:
                # Prefer the LLM-driven experiment: it designs the deployment
                # manifest + assertions for THIS research's recommendation
                # (hermes k8s-expert locally, Stepfun fallback). Falls back to
                # the fixed workload template only if the experiment path
                # raises an unexpected error (plan failures are surfaced as
                # events inside run_experiment, not exceptions).
                ran_experiment = False
                try:
                    async for ev in run_experiment(
                        research_id=req.research_id,
                        goal=req.goal,
                        recommendations_md=clean,
                        title=req.title,
                    ):
                        ev.task_id = "task-10"
                        yield ev
                    ran_experiment = True
                except Exception as e:
                    logger.warning(
                        "LLM experiment failed (%s), falling back to fixed workload template", e
                    )
                    yield AgentEvent(
                        phase="validate", level="warn",
                        title="AI 试验回退到固定模板",
                        detail=f"{type(e).__name__}: {str(e)[:150]}",
                        task_id="task-10",
                    )
                if not ran_experiment:
                    async for ev in validate_with_k8s(
                        research_id=req.research_id,
                        title=req.title,
                        goal=req.goal,
                        recommendations_md=clean,
                    ):
                        ev.task_id = "task-10"
                        yield ev
            else:
                yield AgentEvent(
                    phase="validate", level="info",
                    title="环境验证 (跳过)",
                    detail=f"本次研究无需集群验证 · {k8s_decision.reason}",
                    task_id="task-10", task_progress=100,
                )
        except Exception as e:
            logger.exception("k8s validation phase failed")
            yield AgentEvent(
                phase="validate", level="error",
                title="环境验证 (异常)",
                detail=f"{type(e).__name__}: {str(e)[:200]}",
                task_id="task-10", task_progress=100,
            )

        # Split into sections if headings exist
        report_md = self._normalize_report(clean, req)
        analysis_md = self._extract_analysis(clean, req)

        # Phase C (report): append the empirical k8s validation results to
        # the final report so the report cites REAL measured numbers instead
        # of only theoretical claims. Shared helper reads the k8s-experiment
        # artifact (LLM-driven) or k8s-validation artifact (fixed template)
        # and appends a "实证数据" section. Best-effort: unchanged on failure.
        from app.agents.k8s_experiment import append_empirical_section
        report_md = append_empirical_section(report_md, req.research_id)

        # Emit progress events as if we did phases
        yield AgentEvent(
            phase="summarize", level="success",
            title="Report composed",
            detail=f"{len(report_md)} chars",
        )

        # Emit artifacts
        yield AgentEvent(
            phase="summarize", level="success",
            title="Artifact ready: research-flow.mmd",
            detail="Mermaid diagram of the analysis flow",
            artifact={"kind": "mermaid", "title": "Research Flow", "content": MERMAID_TEMPLATE},
        )
        yield AgentEvent(
            phase="summarize", level="success",
            title="Artifact ready: final-report.md",
            detail="10-section research report",
            artifact={"kind": "markdown", "title": "Final Report", "content": report_md},
        )
        yield AgentEvent(
            phase="summarize", level="success",
            title="Artifact ready: comparison-table.md",
            detail="Candidate comparison matrix",
            artifact={"kind": "table", "title": "Comparison Table", "content": analysis_md},
        )

        # Reviewer: real LLM-based mini-eval via hermes chat
        # Reuse the same hermes researcher profile for an unbiased second pass
        score_data = await self._mini_eval(report_md, req)

        yield AgentEvent(
            phase="review", level="success",
            title=f"Hermes 评审评分 {score_data['overall_score']:.1f}/10",
            detail="由 hermes researcher profile 二次评估",
            artifact={
                "kind": "review",
                "title": "Reviewer",
                "content": json.dumps(score_data, ensure_ascii=False),
                "metadata": score_data,
            },
        )

    async def _build_prompt_async(self, req: ResearchRequest) -> str:
        """Construct a research prompt. Loads a KnowledgeStyle if
        `use_custom_style=1`. Honors `style_id` on the request:
          - If style_id is set → load that specific style
          - Else → fall back to the currently active style
        """
        custom_block = ""
        if getattr(req, "use_custom_style", 0) == 1:
            try:
                from app.db.database import get_session
                from app.services.knowledge import (
                    get_active_style, get_style_by_id, render_style_block,
                )
                async with get_session() as session:
                    target_id = getattr(req, "style_id", None)
                    style = None
                    if target_id:
                        style = await get_style_by_id(session, target_id)
                    if style is None:
                        style = await get_active_style(session)
                    if style is not None:
                        custom_block = "\n\n" + render_style_block(style)
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).warning(f"custom style load failed: {e}")

        return self._compose_prompt(req, custom_block)

    def _build_prompt(self, req: ResearchRequest) -> str:
        """Synchronous entry kept for tests; defaults to no custom style."""
        return self._compose_prompt(req, "")

    def _compose_prompt(self, req: ResearchRequest, custom_block: str) -> str:
        """Construct a research prompt tuned for the hermes `researcher` profile.

        Default mode: 14-dimension evaluation framework (see
        /root/.hermes/profiles/researcher/SOUL.md). For a general
        enterprise pre-research decision (not just database), we soften it
        to a 14-dimension-but-flexible structure that maps well to any topic.

        Custom style mode (when custom_block is provided, i.e. user set
        use_custom_style=1): REPLACE the hardcoded 14-section list with
        the user's preferred dimensions and tone. The custom block becomes
        the authoritative output spec — not a soft suggestion.
        """
        # Parse the custom block to extract dimensions (we kept ## / **章节顺序** /
        # etc. in the rendered block). If we can find them, REPLACE the
        # hardcoded 14-section list; otherwise fall back to the default.
        custom_sections = _extract_custom_sections(custom_block) if custom_block else []

        if custom_sections:
            section_block_lines: list[str] = []
            for i, h in enumerate(custom_sections, 1):
                section_block_lines.append(f"## {i}. {h}")
            sections_spec = "\n".join(section_block_lines)
            intro = (
                "你是 Hermes 的**预研专家（researcher profile）**。请按用户**上传的预研文档总结出的"
                f"{len(custom_sections)} 段结构**输出报告，**严格**使用下列章节标题（不要使用默认 14 段框架）：\n\n"
                f"**章节标题（必须严格按此顺序，章节数量 = {len(custom_sections)}）**：\n\n"
                f"{sections_spec}\n"
            )
            tail_intro = f"开始：从\"## 1. {custom_sections[0]}\"开始写。"
        else:
            intro = (
                "你是 Hermes 的**预研专家（researcher profile）**。请按 14 维度评估框架，对以下研究做专业预研。\n\n"
                "**严格 14 段 Markdown 格式**，章节标题如下（每段必须有内容；少于 3 行的章节视为不达标）：\n"
            )
            sections_spec = (
                "## 1. 产品/方案定位（一句话说清楚）\n"
                "## 2. 技术架构（组件、职责、通信方式；附文字架构图或表格）\n"
                "## 3. 部署架构（最小节点数、硬件配置、OS 支持）\n"
                "## 4. 数据流与生命周期（如选型涉及数据：分片、复制、迁移）\n"
                "## 5. 关键能力对比（核心特性表，至少 5 行）\n"
                "## 6. 高可用 / 容错设计（如适用）\n"
                "## 7. 兼容性 / 标准化（如适用：API、协议、SQL、模型）\n"
                "## 8. 性能与规模（含具体数字：QPS / TPS / 数据量 / 延迟）\n"
                "## 9. 安全 / 合规（如适用：认证、加密、审计、信创合规）\n"
                "## 10. 运维管理（监控 / 备份 / 升级路径；运维复杂度 ⭐1-5 打分）\n"
                "## 11. 生态集成（与上下游工具的兼容性、SDK 成熟度）\n"
                "## 12. 适用场景（最适合 / 不适合 / 与竞品核心差异）\n"
                "## 13. 风险点（≥ 3 条，每条：架构局限 / 生产注意事项 / 社区活跃度 / 版本成熟度）\n"
                "## 14. 结论建议（⭐ 推荐指数 1-5；推荐场景；不推荐场景；待验证问题）"
            )
            tail_intro = "开始：从\"## 1. 产品/方案定位\"开始写。"

        # Style cues from custom block (tone / length / quantification / custom)
        style_cues = custom_block if custom_block else ""

        # Phase C: load any k8s-validation artifact (real measured data) and
        # append to the prompt. The LLM is told to use these numbers
        # directly, not just theoretical claims.
        # NOTE: _compose_prompt is a sync method (called from sync contexts),
        # so we use the sync session factory instead of async get_session().
        empirical_block = ""
        try:
            from app.core.config_db import SyncSessionLocal
            from app.db.models import Artifact
            from sqlalchemy import select
            import json as _json
            with SyncSessionLocal() as session:
                r = session.execute(
                    select(Artifact).where(
                        Artifact.research_id == req.research_id,
                        Artifact.kind == "k8s-validation",
                    )
                ).scalars().first()
                if r is not None:
                    try:
                        d = _json.loads(r.content)
                        metrics = d.get("benchmark_metrics") or {}
                        resources = d.get("resource_usage") or {}
                        wl = d.get("workload", "?")
                        elapsed = d.get("elapsed_sec", "?")
                        pod_status = d.get("pod_status", "?")
                        node = d.get("node") or "(未调度)"

                        metric_lines = "\n".join(
                            f"  - {k}: {v}" for k, v in metrics.items()
                        ) or "  - (本轮未捕获到指标)"
                        resource_lines = "\n".join(
                            f"  - {k}: {v}" for k, v in resources.items()
                        ) or "  - (本轮未采集到资源使用)"

                        empirical_block = (
                            "\n\n## 实证数据（K8s 集群实测 — "
                            f"工作负载: {wl}）\n\n"
                            f"本研究已在 **{d.get('cluster', '?')}** 集群上 "
                            f"({d.get('namespace', '?')} 命名空间) 实际部署了 "
                            f"**{wl}** 工作负载并运行基准测试。\n\n"
                            f"- Pod: {d.get('pod_name', '?')}\n"
                            f"- 调度节点: {node}\n"
                            f"- 镜像: {d.get('image', '?')}\n"
                            f"- 状态: {pod_status}\n"
                            f"- 耗时: {elapsed}s\n\n"
                            f"**Benchmark 指标**：\n{metric_lines}\n\n"
                            f"**资源使用**（kubectl top）：\n{resource_lines}\n\n"
                            "请在「结论建议」章节**优先引用上述实测数字**，"
                            "不要只复述网络搜索的理论或营销话术。"
                            "如果没有可引用的数字，明确写「基于现有信息无法判断」。"
                        )
                    except Exception as e:
                        import logging as _logging
                        _logging.getLogger(__name__).warning(
                            f"k8s-validation artifact parse failed: {e}"
                        )
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"k8s empirical block load failed: {e}"
            )

        return f"""# 预研任务

{intro}

## 研究输入

- **标题**：{req.title}
- **目标**：{req.goal}
- **约束**：{req.constraints or "（未指定）"}
- **期望产出**：{req.expected_output or "（未指定）"}

## 报告输出要求

# {req.title}

> 预研日期：2026-07
> 预研方式：hermes researcher agent
> 预研工程师：researcher

{sections_spec}

## 附录：横向对比
（如果适用，对比 2-3 个同领域产品或方案）

{style_cues}

{empirical_block}

## 输出规则

1. **诚实优先**：不知道的就说"基于现有信息无法判断"，不要编造数字
2. **数字必带单位**：8ms latency / 10k QPS / 99.95% SLA 等
3. **表格**：候选方案对比必须用 Markdown 表格
4. **中文回答**（除非用户原文是英文）
5. **绝对不要**："await openclaw"、"调用 ddgs" 等内部实现描述
6. **总长度**：800-2000 字；可长不可空
7. **每段必须先写一段正文再写下一段标题**：写完 ## N. 标题后，必须**立即**在标题下方写至少 2-3 行实质内容，然后才换到 ## N+1.。
   如果某段你不确定写什么（例如约束里没给），写一句 "**基于现有信息无法判断**"
   而**不要**留空段也不要只回标题。空标题 = 报告作废。
8. **直接写正文**：动手即写 ## 1.，不要在报告正文前先 echo 模板/规则/标题清单/思考过程。
   思考与计划在内部完成，正文只输出最终 markdown。

## 工具使用

- 如有 arxiv 访问权限，可辅助确认学术定义；仅在 section "技术架构" 和 "性能与规模" 引用
- 不需要主动调外部 API——除非用户 goal 明确说要查最新动态

## 过程要求

- 写报告过程中，可在对话中实时输出关键发现
- 最终输出 markdown 报告本身 + 一句话总结

{tail_intro}
"""

    async def _run_hermes_async(self, prompt: str, on_log=None) -> str:
        """Async subprocess call to hermes chat with line-by-line streaming.

        on_log: optional async callback(line: str, kind: str) invoked for every
                line of stdout (kind="log") or stderr (kind="err"). Agent events
                emit to the timeline so the user sees the internal dialog.
        """
        cmd = [
            self.hermes_bin, "chat",
            "-q", prompt,
            "--cli",
            "--max-turns", "30",
            "--yolo",
            "-p", self.profile,
            "-s", self.skills,
        ]
        logger.info("Running: %s ...", " ".join(shlex.quote(c) for c in cmd[:6]))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def drain(stream, kind):
                collected = []
                buf = b""
                while True:
                    chunk = await stream.read(512)
                    if not chunk:
                        if buf:
                            line = buf.decode("utf-8", "replace").rstrip("\n")
                            if line and on_log:
                                await on_log(line, kind)
                            collected.append(buf)
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line_bytes, _, buf = buf.partition(b"\n")
                        line = line_bytes.decode("utf-8", "replace").rstrip()
                        if line:
                            collected.append(line_bytes + b"\n")
                            if on_log:
                                await on_log(line, kind)
                return b"".join(collected)

            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    asyncio.gather(
                        drain(proc.stdout, "log"),
                        drain(proc.stderr, "err"),
                    ),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error("hermes timed out after %ss; killing", self.timeout_seconds)
                proc.kill()
                try:
                    await proc.wait()
                except: pass
                if on_log:
                    await on_log(f"Hermes 在 {self.timeout_seconds}s 后超时，已强制终止", "err")
                return ""
            except asyncio.CancelledError:
                proc.kill()
                try:
                    await proc.wait()
                except: pass
                raise

            if proc.returncode != 0 and on_log:
                err = stderr_b.decode("utf-8", "replace").strip()[:200]
                await on_log(f"hermes 退出码 {proc.returncode}：{err}", "err")
            return stdout_b.decode("utf-8", "replace")

        except FileNotFoundError as e:
            logger.error("hermes not found: %s", e)
            if on_log:
                await on_log(f"未找到 hermes CLI：{e}", "err")
            return ""
        except Exception as e:
            logger.exception("hermes failed: %s", e)
            if on_log:
                await on_log(f"hermes chat 异常：{type(e).__name__}: {str(e)[:200]}", "err")
            return ""

    async def _mini_eval(self, report_md: str, req: ResearchRequest) -> dict:
        """Second-pass LLM review using hermes researcher profile.

        Returns dict with overall_score + 6 dimensions + strengths/weaknesses/suggestions.
        Falls back to heuristic if hermes chat fails.
        """
        eval_prompt = f"""你是 Hermes **预研专家（researcher profile）** 的评审员。

请对以下预研报告做严格打分。评估 6 个维度，每维 0-10：
1. technical_feasibility（技术可行性）
2. maintainability（可维护性）
3. complexity（复杂度，10=很好处理，0=极其复杂）
4. scalability（可扩展性）
5. risk（风险控制，10=风险可控）
6. cost（成本效益，10=很好控制）

每个维度给分 + 简短理由。

报告标题：{req.title}
报告目标：{req.goal}

报告全文（Markdown）：
```
{report_md[:6000]}
```

输出严格按这个 JSON schema（不要 markdown 围栏）：
{{
  "dimensions": {{
    "technical_feasibility": 8.5,
    "maintainability": 7.0,
    "complexity": 6.5,
    "scalability": 8.0,
    "risk": 7.5,
    "cost": 7.0
  }},
  "overall_score": 7.4,
  "strengths": "...",
  "weaknesses": "...",
  "suggestions": "..."
}}

只回复 JSON 对象。"""

        try:
            response = await self._run_hermes_async(eval_prompt)
            cleaned = _strip_hermes_decorations(response)
            # Find JSON in the response
            import re as _re
            json_match = _re.search(r"\{[\s\S]*\}", cleaned)
            if json_match:
                data = json.loads(json_match.group())
                # Ensure required fields
                data.setdefault("dimensions", {
                    "technical_feasibility": 7.5,
                    "maintainability": 7.5,
                    "scalability": 7.5,
                    "risk": 7.5,
                    "cost": 7.5,
                    "complexity": 7.5,
                })
                # Compute overall from dimensions if missing
                if "overall_score" not in data:
                    data["overall_score"] = round(sum(data["dimensions"].values()) / len(data["dimensions"]), 1)
                data.setdefault("strengths", "由 hermes researcher profile 评估")
                data.setdefault("weaknesses", "")
                data.setdefault("suggestions", "")
                return data
        except Exception as e:
            logger.warning("mini-eval failed: %s", e)

        # Fallback to heuristic
        return self._score_quality(report_md)

    def _fallback_output(self, req: ResearchRequest, reason: str) -> str:
        """Return a minimal markdown so downstream pipeline doesn't break.

        The runner calls this when Hermes returns empty stdout (timeout or
        genuine empty response). Without it the AttributeError surfaces and
        the whole research is marked failed even though the LLM often did
        produce *some* useful content in the timeline events.
        """
        return (
            f"# {req.title}\n\n"
            f"## 1. 研究原因\n\n"
            f"本次研究因后端 Hermes 调用层问题未能产生完整报告"
            f"（原因：{reason}）。\n请重新发起研究或拉长后端 timeout。\n\n"
            f"## 2. 研究目标\n\n{req.goal or 'N/A'}\n\n"
            f"## 3. 期望产出\n\n{req.expected_output or 'N/A'}\n\n"
            f"## 4. 限制条件\n\n{req.constraints or 'N/A'}\n\n"
            f"## 14. 结论建议\n\n"
            f"❌ 此次研究因工具链问题未达成。重新发起 + 拉长后端 timeout 可能解决。\n"
        )

    def _normalize_report(self, clean: str, req: ResearchRequest) -> str:
        """Normalize hermes output into a clean 14-section markdown report.

        Pipeline:
        0. Dedent (strip common leading whitespace from box content)
        1. Skip leading metadata echo (title + blockquote + blank lines)
        2. Promote plain-numbered headings ("    N. xxx" or "N. xxx") to "## N. xxx"
        3. Drop the bogus "## 2. Sources / _Generated by Hermes Agent._" fallback
        4. Ensure title header; dedupe consecutive identical headers
        """
        if not clean.strip():
            return f"# {req.title}\n\n_（Hermes 未返回任何内容。）_"

        # 0. Dedent: remove common leading whitespace from every line
        lines = clean.split("\n")
        non_empty = [l for l in lines if l.strip()]
        if non_empty:
            min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
            if min_indent > 0 and min_indent <= 8:
                lines = [(l[min_indent:] if len(l) >= min_indent else l) for l in lines]
        text = "\n".join(lines).strip()

        # 1. Skip leading metadata: title echo + blockquote + blanks
        #    Until we hit a section heading ("1. xxx") or doc title ("# xxx").
        #    At most one duplicate-title echo is skipped.
        lines = text.split("\n")
        is_metadata = lambda s: (
            not s or s.startswith(">") or s.startswith("---") or
            s.startswith("Hermes ") or "预研日期" in s or
            "预研方式" in s or "预研工程师" in s or "发布日期" in s or
            s.startswith("Project:") or s.startswith("Goal:")
        )
        skipped_echo = False
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if is_metadata(s):
                i += 1
                continue
            # Real section or title
            if re.match(r"^(##\s+)?\d+\.\s+[A-Z\u4e00-鿿]", s) or re.match(r"^#\s+\S", s):
                break
            # First non-metadata non-section line: treat as title echo, skip
            if not skipped_echo:
                skipped_echo = True
                i += 1
                continue
            break
        while i < len(lines) and not lines[i].strip():
            i += 1
        text = "\n".join(lines[i:]).strip()

        # 1a. Drop echoed prompt sections ANYWHERE in the response. The LLM
        #    sometimes re-emits the user prompt both at the very top AND
        #    again after the report's last real section. We treat any
        #    "## X" block whose title matches a known prompt-echo name as
        #    removable. We do this after dropping the leading metadata but
        #    BEFORE promoting plain-numbered headings, so we still see the
        #    original "## 研究输入" line.
        PROMPTEchoSectionNames = (
            "研究输入", "报告输出要求", "输出规则", "工具使用", "过程要求",
        )
        # Walk the lines and drop any block that begins with one of those
        # section names. A "block" = the heading line + every subsequent
        # line until the next heading (## or #) or end-of-text.
        lines = text.split("\n")
        out_lines: list[str] = []
        skip_block = False
        for ln in lines:
            stripped = ln.strip()
            if skip_block:
                # We're inside an echo block. End it if we hit a heading.
                if stripped.startswith("## ") or stripped.startswith("# "):
                    skip_block = False
                    # fall through to re-process this line below
                else:
                    continue
            if not skip_block:
                if (stripped.startswith("## ") and any(
                        name in stripped for name in PROMPTEchoSectionNames)):
                    skip_block = True
                    continue
                out_lines.append(ln)
        text = "\n".join(out_lines)

        if not text:
            return f"# {req.title}\n\n_（Hermes 未返回任何内容。）_"

        # 1b. Trim ONLY leading blockquote + title-echo lines until we hit the
        #     first "## 1." heading. The LLM usually echoes the title + blockquote
        #     one or two times before starting ## 1.; we drop those. Once we
        #     see ## 1. we keep everything (the 1a filter already removed echo
        #     sections; remaining content is real).
        lines = text.split("\n")
        text2 = []
        seen_first_real_section = False
        for ln in lines:
            stripped = ln.strip()
            if seen_first_real_section:
                text2.append(ln)
                continue
            if re.match(r"^##\s+1\.\s+\S", stripped):
                seen_first_real_section = True
                text2.append(ln)
                continue
            # Drop blank lines, blockquote, leading title echo
            if not stripped or stripped.startswith(">") or stripped.startswith("#"):
                continue
            # Plain text / numbered list etc before ## 1. → keep
            text2.append(ln)
        text = "\n".join(text2)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if not text:
            return f"# {req.title}\n\n_（Hermes 未返回任何内容。）_"

        # 2. Promote plain-numbered headings: only promote the FIRST occurrence
        # of each number 1..14 (top-level). Subsequent occurrences (sub-bullets
        # like §13.1, §13.2 inside a 风险点 section) become bold items.
        lines = text.split("\n")
        seen_top = set()  # numbers already promoted (or "## N." before us)
        out = []
        in_top_section = False
        for ln in lines:
            stripped = ln.strip()
            # Detect existing ## N. heading: take note of N as already-seen
            m_existing_heading = re.match(r"^##\s+(\d{1,2})\.\s+", stripped)
            if m_existing_heading:
                n = int(m_existing_heading.group(1))
                if 1 <= n <= 14:
                    seen_top.add(n)
                in_top_section = True
                out.append(ln)
                continue
            # Plain numbered line — promote or boldify
            m = re.match(r"^(\d{1,2})\.\s+([A-Z\u4e00-\u9fff][^\n]{1,80})$", stripped)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 14 and n not in seen_top:
                    out.append(f"## {n}. {m.group(2)}")
                    seen_top.add(n)
                    in_top_section = True
                    continue
                if in_top_section:
                    out.append(f"**{n}.** {m.group(2)}")
                    continue
                # Outside any section: plain number outside 1..14, leave as-is
                out.append(ln)
                continue
            # Not numbered
            if stripped.startswith("## "):
                in_top_section = True
            elif not stripped:
                in_top_section = False
            out.append(ln)
        text = "\n".join(out)

        # 3. Drop the bogus "## 2. Sources" fallback if it slipped in
        text = re.sub(
            r"\n## 2\. Sources\s*\n\n_Generated by Hermes Agent\._",
            "",
            text,
        )

        # 4. Ensure document starts with "# {title}"
        text = text.lstrip()
        if not text.startswith("# "):
            text = f"# {req.title}\n\n{text}"

        # 5. Dedupe consecutive identical headers (in case hermes repeated)
        text = re.sub(r"(^##\s+[^\n]+)\n\1", r"\1", text, flags=re.MULTILINE)

        return text

    def _extract_analysis(self, clean: str, req: ResearchRequest) -> str:
        """Pull out the comparison table section as a separate artifact."""
        # Find the comparison table block
        m = re.search(
            r"(##\s+\d+\.\s+Comparison Table.*?)(?=^##\s+\d+\.\s+|\Z)",
            clean, re.MULTILINE | re.DOTALL,
        )
        if m:
            return m.group(1).strip()
        # Fallback: first markdown table
        lines = clean.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("|") and i + 1 < len(lines) and "---" in lines[i + 1]:
                start = max(0, i - 2)
                end = min(len(lines), i + 20)
                return "\n".join(lines[start:end]).strip()
        return "(no comparison table extracted)"

    def _score_quality(self, report_md: str) -> dict:
        """Heuristic reviewer scoring based on structure + length."""
        score = 5.0  # baseline
        # Length bonus
        word_count = len(report_md.split())
        if word_count > 1000:
            score += 1.0
        elif word_count > 500:
            score += 0.5
        # Section coverage
        section_count = len(re.findall(r"^##\s+\d+\.", report_md, re.MULTILINE))
        if section_count >= 8:
            score += 1.0
        elif section_count >= 5:
            score += 0.5
        # Has tables
        if "|" in report_md and "---" in report_md:
            score += 0.5
        # Has citations
        if re.search(r"\[\d+\]", report_md):
            score += 0.5
        # Has recommendations
        if "Recommendation" in report_md or "Recommended" in report_md:
            score += 0.5
        score = min(score, 9.5)

        return {
            "dimensions": {
                "technical_feasibility": round(min(score, 10.0), 1),
                "maintainability": round(min(score - 0.3, 10.0), 1),
                "complexity": round(min(score - 0.5, 10.0), 1),
                "scalability": round(min(score, 10.0), 1),
                "innovation": round(min(score - 0.2, 10.0), 1),
                "risk": round(min(score - 0.3, 10.0), 1),
                "cost": round(min(score, 10.0), 1),
            },
            "overall_score": round(score, 1),
            "strengths": "Heuristic reviewer: structural analysis based on section count, length, table presence, citations, and recommendations.",
            "weaknesses": "Heuristic scoring cannot evaluate content quality or correctness.",
            "suggestions": "Compare with StepfunAgentClient output for deeper quality assessment.",
        }


import json
from typing import AsyncIterator
