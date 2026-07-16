import json
import logging
"""StepfunAgentClient: real LLM-driven research execution.

Implements AgentClient using step-3.7-flash + DDGS search.

Yield sequence per research:
  1. 10 task-tree events (mirrors mock)
  2. timeline events for each phase: understand -> research -> analyze -> report -> review
  3. artifact events: mermaid flow + markdown report + comparison table + review
"""
import asyncio
import json
import logging
from typing import AsyncIterator

from app.agents.base import AgentClient, AgentEvent, ResearchRequest
from app.agents.llm import StepfunClient, LLMError, _strip_thinking
from app.agents.search import DDGSSearch
from app.agents.prompts import (
    UNDERSTAND_SYSTEM, UNDERSTAND_USER_TEMPLATE,
    RESEARCH_SYSTEM, RESEARCH_USER_TEMPLATE,
    ANALYZE_SYSTEM, ANALYZE_USER_TEMPLATE,
    REPORT_SYSTEM, REPORT_USER_TEMPLATE,
    REVIEWER_SYSTEM, REVIEWER_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


def _llm_event(action: str, phase: str, detail: str = "") -> AgentEvent:
    """Create a timeline event for LLM traces."""
    level: LogLevel = "info"
    if "←←" in action:
        level = "success"
    elif "→→" not in action:
        level = "warn"
    return AgentEvent(
        phase=phase,
        level=level,
        title=action,
        detail=detail[:200] if detail else "",
    )


def _trace_request(system: str, user: str, max_tokens: int = 0, phase: str = "") -> str:
    sz = len(system or "") + len(user or "")
    model = max_tokens
    return f"prompt={sz} 字符 · model.max_tokens={model} · phase={phase}"


def _trace_response(text) -> str:
    """Extract a one-line snippet from LLM response for Console."""
    if isinstance(text, (dict, list)):
        s = json.dumps(text, ensure_ascii=False)
    else:
        s = str(text)
    flat = " ".join(s.split())
    return (flat[:200] + ("\u2026" if len(flat) > 200 else ""))


# Reuse the task-tree shape from mock for UI consistency
TASK_TREE = [
    ("requirement", "需求分析", "将研究目标拆解为原子问题"),
    ("research", "信息收集", "在互联网和内部知识库中检索一手资料"),
    ("research", "来源筛选", "按可信度、时效性和相关性筛选"),
    ("research", "深度阅读", "提取关键论断、数据和反面观点"),
    ("comparison", "对比分析", "构建候选方案的对比矩阵"),
    ("comparison", "权衡映射", "结合约束条件映射权衡点"),
    ("evaluation", "可行性评分", "按技术 / 成本 / 风险维度评分"),
    ("evaluation", "风险识别", "识别运维、安全和组织风险"),
    ("report", "综合写作", "撰写执行摘要和推荐方案"),
    ("report", "评审打分", "运行 AI 评审员给出客观分数"),
]


# Review dimensions used by the reviewer prompt and the Review row
REVIEW_DIMENSIONS = [
    "technical_feasibility", "maintainability",
    "scalability", "innovation", "risk", "cost",
]


MERMAID_TEMPLATE = """graph TD
    A[Research Goal] --> B[Requirement Analysis]
    B --> C[Information Gathering]
    B --> D[Trade-off Discovery]
    C --> E[Comparison Matrix]
    D --> E
    E --> F[Recommended Solution]
    E --> G[Risk Register]
    F --> H[Implementation Plan]
    G --> H
    H --> I[Final Report]

    style A fill:#1e40af,stroke:#1e3a8a,color:#fff
    style F fill:#059669,stroke:#047857,color:#fff
    style H fill:#7c3aed,stroke:#5b21b6,color:#fff
    style I fill:#ea580c,stroke:#c2410c,color:#fff
"""


class StepfunAgentClient(AgentClient):
    """Real LLM-driven research. Falls back to a minimal stub on LLM failure."""

    def __init__(
        self,
        api_key: str,
        model: str = "step-3.7-flash",
        base_url: str = "https://api.stepfun.com/step_plan/v1",
    ):
        self.llm = StepfunClient(api_key=api_key, base_url=base_url, model=model)
        self.searcher = DDGSSearch(max_results=4)

    async def run_research(self, req: ResearchRequest) -> AsyncIterator[AgentEvent]:
        # 1) Task tree (UI consistency)
        for idx, (phase, name, desc) in enumerate(TASK_TREE):
            yield AgentEvent(
                phase=phase, level="info",
                title=f"任务 {idx + 1}/{len(TASK_TREE)}: {name}",
                detail=desc,
                task_id=f"task-{idx:02d}", task_progress=0,
            )

        findings = ""
        analysis = ""
        report_md = ""
        review_payload: dict = {}
        image_md = ""  # safety: defined even if research phase skipped

        try:
            # Phase 1: UNDERSTAND
            yield AgentEvent(phase="understand", level="info",
                             title="理解研究目标", detail="通过 LLM 拆解")
            yield AgentEvent(phase="understand", level="info",
                             title="拆解为子问题",
                             detail="让 LLM 将目标拆为原子问题",
                             task_id="task-00", task_progress=50)

            user_msg = UNDERSTAND_USER_TEMPLATE.format(
                title=req.title, goal=req.goal,
                constraints=req.constraints or "(none)",
                expected_output=req.expected_output or "(none)",
            )
            try:
                plan = await self.llm.chat_json(UNDERSTAND_SYSTEM, user_msg, max_tokens=4000, temperature=0.3)
                sub_questions = plan.get("sub_questions") or []
                search_queries = plan.get("search_queries") or []
                yield AgentEvent(phase="decompose", level="success",
                                 title=f"Decomposed into {len(sub_questions)} sub-questions",
                                 detail="; ".join(sub_questions[:3]))
            except LLMError as e:
                logger.warning("understand phase LLM failed: %s", e)
                sub_questions = [req.goal]
                search_queries = [req.goal]
                yield AgentEvent(phase="decompose", level="warn",
                                 title="子问题降级处理",
                                 detail="直接使用原目标作为单一问题")

            yield AgentEvent(phase="understand", level="success",
                             title="需求分析完成",
                             detail="", task_id="task-00", task_progress=100)

            # Phase 2: RESEARCH
            yield AgentEvent(phase="search", level="info",
                             title=f"检索网络：{len(search_queries)} 个查询",
                             detail="使用 DuckDuckGo（无需 API key）",
                             task_id="task-01", task_progress=0)
            hits = self.searcher.search_many(search_queries)
            yield AgentEvent(phase="search", level="info",
                             title=f"找到 {len(hits)} 个资料源",
                             detail="按 URL 去重")


            # Also search for images
            yield AgentEvent(phase="search", level="info",
                             title="图片检索中",
                             detail=", ".join(search_queries[:3])[:100])
            image_hits = self.searcher.search_images_many(search_queries[:3], max_per_query=2)
            yield AgentEvent(phase="search", level="success",
                             title=f"找到 {len(image_hits)} 张图片",
                             detail="DDGS 图片搜索")
            # Format images as markdown
            if image_hits:
                image_md = "\n\n".join(
                    f"![{img.get('title', 'image')}]({img['image_url']})"
                    for img in image_hits[:6]
                )
            # Read events (sample first 5 hits)
            for i, (q, h) in enumerate(hits[:5]):
                yield AgentEvent(phase="read", level="info",
                                 title=f"阅读资料 {i + 1}/{min(len(hits), 5)}",
                                 detail=f"{h.title[:60]} — {h.url[:60]}")

            yield AgentEvent(phase="read", level="info",
                             title="综合研究结论",
                             detail="让 LLM 提取关键论断",
                             task_id="task-03", task_progress=50)

            # Format hits for the LLM
            if hits:
                sources_md = "\n".join(
                    f"[{i + 1}] {h.title}\n    URL: {h.url}\n    {h.snippet}"
                    for i, (_, h) in enumerate(hits)
                )
            else:
                sources_md = "(no web results — proceeding from model knowledge only)"

            try:
                findings = await self.llm.chat(
                    RESEARCH_SYSTEM,
                    RESEARCH_USER_TEMPLATE.format(
                        goal=req.goal,
                        constraints=req.constraints or "(none)",
                        sub_questions="\n".join(f"- {q}" for q in sub_questions),
                        search_results=sources_md,
                    ),
                    max_tokens=3000,
                )
                yield AgentEvent(phase="analyze", level="success",
                                 title="研究结论已综合",
                                 detail=f"{len(findings)} 字符，{len(hits)} 个资料源")
            except LLMError as e:
                logger.warning("research phase LLM failed: %s", e)
                findings = (
                    f"## Findings (fallback)\n\n"
                    f"Web search surfaced {len(hits)} sources for: {req.goal}.\n\n"
                    f"Key sources:\n" + "\n".join(f"- [{h.title}]({h.url})" for _, h in hits[:5])
                )
                yield AgentEvent(phase="analyze", level="warn",
                                 title="研究结论降级处理",
                                 detail="LLM 综合不可用，使用原始资料列表")

            yield AgentEvent(phase="read", level="success",
                             title="深度阅读完成",
                             detail="", task_id="task-03", task_progress=100)

            # Phase 3: ANALYZE
            yield AgentEvent(phase="analyze", level="info",
                             title="构建对比矩阵",
                             detail="让 LLM 对比候选方案",
                             task_id="task-04", task_progress=0)
            try:
                analysis_prompt = ANALYZE_USER_TEMPLATE.format(
                    goal=req.goal, findings=findings[:4000])
                yield _llm_event("→→ analyze prompt", "analyze", analysis_prompt[:120])
                analysis = await self.llm.chat(
                    ANALYZE_SYSTEM,
                    analysis_prompt,
                    max_tokens=1500,
                )
                yield _llm_event("←← analyze result", "analyze", f"{len(analysis)} chars")
                yield AgentEvent(phase="analyze", level="success",
                                 title="对比分析完成",
                                 detail=f"{len(analysis)} 字符")
            except LLMError as e:
                logger.warning("analyze phase LLM failed: %s", e)
                analysis = "(Analysis unavailable)"
                yield AgentEvent(phase="analyze", level="warn",
                                 title="对比分析降级处理", detail=str(e)[:80])

            yield AgentEvent(phase="analyze", level="success",
                             title="对比分析完成",
                             detail="", task_id="task-04", task_progress=100)

            # Phase 4: REPORT
            yield AgentEvent(phase="summarize", level="info",
                             title="起草执行摘要",
                             detail="让 LLM 撰写完整 10 节报告",
                             task_id="task-08", task_progress=0)
            try:
                report_md = await self.llm.chat(
                    REPORT_SYSTEM,
                    REPORT_USER_TEMPLATE.format(
                        title=req.title, goal=req.goal,
                        constraints=req.constraints or "(none)",
                        expected_output=req.expected_output or "(none)",
                        findings=findings[:4000],  # reduced from 5000 to leave room for output
                        analysis=analysis[:2000],  # reduced from 2500
                        images=image_md or "(none)",
                    ),
                    max_tokens=16000,  # bumped from 8000 — 12-section report needs ~16k tokens
                )
                report_md = _strip_thinking(report_md, is_json=False)  # remove "Got it, let's..." preamble
            except LLMError as e:
                # One retry with smaller prompt
                logger.warning("report phase first try failed (%s), retrying", e)
                try:
                    report_md = await self.llm.chat(
                        REPORT_SYSTEM,
                        REPORT_USER_TEMPLATE.format(
                            title=req.title, goal=req.goal,
                            constraints=req.constraints or "(none)",
                            expected_output=req.expected_output or "(none)",
                            findings=findings[:2500],
                            analysis=analysis[:1500],
                            images=image_md or "(none)",
                        ),
                        max_tokens=8000,
                    )
                    report_md = _strip_thinking(report_md, is_json=False)
                except LLMError:
                    raise
                yield AgentEvent(phase="summarize", level="success",
                                 title="报告撰写完成",
                                 detail=f"{len(report_md)} 字符")
            except LLMError as e:
                logger.warning("report phase LLM failed: %s", e)
                # Synthesize a usable report from prior phase outputs
                report_md = (
                    f"# {req.title}\n\n"
                    f"## 1. Executive Summary\n\n"
                    f"_Note: The final report synthesis phase encountered an LLM error ({str(e)[:80]}). "
                    f"The findings and analysis below were generated directly by the agent without a final pass._\n\n"
                    f"This research examined: **{req.goal}**\n\n"
                    f"The full comparison matrix is available in the **Comparison** tab. "
                    f"The detailed findings with source citations are in the **Comparison Table** artifact.\n\n"
                    f"## 2. Research Findings\n\n{findings}\n\n"
                    f"## 3. Comparative Analysis\n\n{analysis}\n\n"
                    f"## 4. Reviewer Note\n\n"
                    f"See the **Reviewer** tab for the quality assessment."
                )
                yield AgentEvent(phase="summarize", level="warn",
                                 title="报告降级处理（合成阶段 LLM 错误）",
                                 detail=f"Findings ({len(findings)} chars) + Analysis ({len(analysis)} chars) preserved as report")

            yield AgentEvent(phase="summarize", level="success",
                             title="最终报告完成",
                             detail="", task_id="task-08", task_progress=100)

            # Phase 5: REVIEWER
            yield AgentEvent(phase="review", level="info",
                             title="评审员评估报告",
                             detail="让 LLM 对 6 个维度评分")
            try:
                review_payload = await self.llm.chat_json(
                    REVIEWER_SYSTEM,
                    REVIEWER_USER_TEMPLATE.format(report=report_md[:5000]),
                    max_tokens=8000,  # bumped to fit thinking + JSON
                    temperature=0.2,  # lower for more deterministic output
                )
                yield AgentEvent(phase="review", level="success",
                                 title=f"评审员评分 {review_payload.get('overall_score', 0):.1f}/10",
                                 detail="6 个维度已评估")
            except LLMError as e:
                logger.warning("reviewer LLM failed: %s", e)
                review_payload = {
                    "dimensions": {k: 7.5 for k in REVIEW_DIMENSIONS},
                    "overall_score": 7.5,
                    "strengths": "评审员不可用，使用默认评分。",
                    "weaknesses": "评审员不可用。",
                    "suggestions": "使用有效的 LLM 凭据重新运行以获取详细反馈。",
                }
                yield AgentEvent(phase="review", level="warn",
                                 title="评审员降级处理", detail=str(e)[:80])

        except Exception as e:
            logger.exception("Unexpected error in StepfunAgentClient")
            yield AgentEvent(phase="review", level="error",
                             title=f"Execution error: {e}", detail="Pipeline aborted")

        # 2) Artifacts (always emit, even if some phases failed)
        yield AgentEvent(
            phase="summarize", level="success",
            title="产物就绪：研究流程图.mmd",
            detail="分析流程的 Mermaid 图",
            artifact={"kind": "mermaid", "title": "Research Flow", "content": MERMAID_TEMPLATE},
        )
        yield AgentEvent(
            phase="summarize", level="success",
            title="产物就绪：最终报告.md",
            detail="10 节研究报告",
            artifact={"kind": "markdown", "title": "Final Report", "content": report_md or "# No report generated"},
        )

        # Comparison table artifact: extract from analysis (look for table block)
        table_md = _extract_table(analysis) if analysis else ""
        yield AgentEvent(
            phase="summarize", level="success",
            title="产物就绪：对比表.md",
            detail="候选方案对比矩阵",
            artifact={"kind": "table", "title": "Comparison Table", "content": table_md or analysis or "(no analysis)"},
        )

        yield AgentEvent(
            phase="review", level="success",
            title="评审员已附加",
            detail=f"总分 {review_payload.get('overall_score', 0):.1f}/10",
            artifact={
                "kind": "review",
                "title": "Reviewer",
                "content": json.dumps(review_payload, ensure_ascii=False),
                "metadata": review_payload,  # executor reads this to persist Review row
            },
        )


def _extract_table(md: str) -> str:
    """Find the first Markdown table in the text. Returns empty string if not found."""
    lines = md.split("\n")
    out: list[str] = []
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|---"):
            # Start of a table
            out.append(line)
            out.append(lines[i + 1])
            for j in range(i + 2, len(lines)):
                if lines[j].strip().startswith("|"):
                    out.append(lines[j])
                else:
                    break
            break
    return "\n".join(out)
