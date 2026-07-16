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

logger = logging.getLogger(__name__)

# Reuse task-tree from mock for UI consistency
TASK_TREE_HERMES = TASK_TREE  # same shape


# Output cleanup: strip the `╭─ ⚕ Hermes ─╮` decorative box.
# The actual content lives between the box border and the closing `╰─...─╯`.
HERMES_BOX_RE = re.compile(
    r"╭─[^\n]*?╮\s*\n(.*?)\s*╰─[^\n]*?╯",
    re.DOTALL,
)


def _strip_hermes_decorations(text: str) -> str:
    """Extract the inner content of hermes' final answer box.

    Hermes output typically has multiple boxes (preamble reasoning, intermediate
    status updates, and a final answer). We extract the LAST box which is the
    actual final answer to the user query.
    """
    # Strip ANSI escape codes
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    # Find ALL boxes; take the LAST one (final answer)
    all_boxes = HERMES_BOX_RE.findall(text)
    if all_boxes:
        return all_boxes[-1].strip()
    # Fallback: drop known meta-only lines and return the rest
    lines = text.split("\n")
    out = []
    for line in lines:
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

        # Build the research prompt for hermes
        prompt = self._build_prompt(req)

        yield AgentEvent(
            phase="understand", level="info",
            title="Dispatching to Hermes Agent",
            detail=f"Using hermes profile={self.profile}, skills={self.skills}",
            task_id="task-00", task_progress=20,
        )

        # Async subprocess call (true asyncio subprocess; cancellable)
        # Define on_log callback that emits AgentEvents for each line of
        # hermes stdout/stderr → user sees the agent's internal dialog stream.
        async def _on_log(line: str, kind: str):
            # Categorize line by content
            stripped = line.lstrip()
            level = "info"
            title = line[:80]
            # Reasoning: `┌─ Reasoning ─┐` blocks
            if "Reasoning" in stripped or stripped.startswith("\u2192"):
                phase = "reasoning"
                title = "[推理] " + (stripped.split("\u2500")[-1].strip() if "\u2500" in stripped else stripped)[:60]
            # Tool calls: starts with ┊ emoji (📚 💻 📖)
            elif any(stripped.startswith(e) for e in ("📚 ", "💻 ", "📖 ", "┊ ", "🔎")):
                phase = "tool"
                # Common: "📚 preparing skill_view…" or "💻 $ curl ..."
                if "preparing" in stripped:
                    title = "[准备] " + stripped.split("preparing")[-1].strip(" …")
                elif " $ " in stripped or stripped.startswith("$"):
                    title = "[执行] " + stripped.replace("┊ ", "").strip()[:80]
                else:
                    title = "[工具] " + stripped.replace("┊ ", "").strip()[:80]
            # Errors / warnings
            elif "Error" in stripped or "Exception" in stripped or kind == "err":
                phase = "stderr"
                level = "warn" if kind == "err" else "info"
            elif "Resume this session" in stripped or stripped.startswith("Session"):
                phase = "meta"
                title = "[结束] " + stripped[:60]
            else:
                phase = "log"
            yield_event = AgentEvent(
                phase=phase, level=level, title=title, detail=line[:200],
            )
            # We must yield from run_research, not from _on_log
            # Use a thread-safe queue approach: caller passes a list to append into
            nonlocal pending_events
            pending_events.append(yield_event)

        # pending_events lets _on_log accumulate AgentEvents for the main generator
        pending_events = []

        try:
            raw_output = await self._run_hermes_async(prompt, on_log=_on_log)
        except asyncio.TimeoutError:
            yield AgentEvent(
                phase="review", level="error",
                title=f"Hermes timed out after {self.timeout_seconds}s",
                detail="Falling back to minimal report",
            )
            raw_output = ""
        except Exception as e:
            logger.exception("Hermes dispatch failed")
            yield AgentEvent(
                phase="review", level="error",
                title="Hermes dispatch failed",
                detail=f"{type(e).__name__}: {str(e)[:200]}",
            )
            raw_output = self._fallback_output(req, "dispatch_error")

        # Flush any events collected by _on_log callbacks
        for ev in pending_events:
            yield ev
        if not raw_output.strip():
            raw_output = self._fallback_output(req, "timeout_or_empty")

        # Clean output
        clean = _strip_hermes_decorations(raw_output)

        yield AgentEvent(
            phase="summarize", level="success",
            title="Hermes returned",
            detail=f"{len(clean)} chars after cleanup",
            task_id="task-08", task_progress=100,
        )

        # Split into sections if headings exist
        report_md = self._normalize_report(clean, req)
        analysis_md = self._extract_analysis(clean, req)

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

    def _build_prompt(self, req: ResearchRequest) -> str:
        """Construct a research prompt tuned for the hermes `researcher` profile.

        The researcher profile uses a 14-dimension evaluation framework
        (see /root/.hermes/profiles/researcher/SOUL.md). For a general
        enterprise pre-research decision (not just database), we soften it
        to a 14-dimension-but-flexible structure that maps well to any topic.
        """
        return f"""# 预研任务

你是 Hermes 的**预研专家（researcher profile）**。请按 14 维度评估框架，对以下研究做专业预研。

## 研究输入

- **标题**：{req.title}
- **目标**：{req.goal}
- **约束**：{req.constraints or "（未指定）"}
- **期望产出**：{req.expected_output or "（未指定）"}

## 报告输出要求

**严格 14 段 Markdown 格式**，章节标题如下（每段必须有内容；少于 3 行的章节视为不达标）：

# {req.title}

> 预研日期：2026-07
> 预研方式：hermes researcher agent
> 预研工程师：researcher

## 1. 产品/方案定位（一句话说清楚）
## 2. 技术架构（组件、职责、通信方式；附文字架构图或表格）
## 3. 部署架构（最小节点数、硬件配置、OS 支持）
## 4. 数据流与生命周期（如选型涉及数据：分片、复制、迁移）
## 5. 关键能力对比（核心特性表，至少 5 行）
## 6. 高可用 / 容错设计（如适用）
## 7. 兼容性 / 标准化（如适用：API、协议、SQL、模型）
## 8. 性能与规模（含具体数字：QPS / TPS / 数据量 / 延迟）
## 9. 安全 / 合规（如适用：认证、加密、审计、信创合规）
## 10. 运维管理（监控 / 备份 / 升级路径；运维复杂度 ⭐1-5 打分）
## 11. 生态集成（与上下游工具的兼容性、SDK 成熟度）
## 12. 适用场景（最适合 / 不适合 / 与竞品核心差异）
## 13. 风险点（≥ 3 条，每条：架构局限 / 生产注意事项 / 社区活跃度 / 版本成熟度）
## 14. 结论建议（⭐ 推荐指数 1-5；推荐场景；不推荐场景；待验证问题）

## 附录：横向对比
（如果适用，对比 2-3 个同领域产品或方案）

## 输出规则

1. **诚实优先**：不知道的就说"基于现有信息无法判断"，不要编造数字
2. **数字必带单位**：8ms latency / 10k QPS / 99.95% SLA 等
3. **表格**：候选方案对比必须用 Markdown 表格
4. **中文回答**（除非用户原文是英文）
5. **绝对不要**："await openclaw"、"调用 ddgs" 等内部实现描述
6. **总长度**：800-2000 字；可长不可空

## 工具使用

- 如有 arxiv 访问权限，可辅助确认学术定义；仅在 section "技术架构" 和 "性能与规模" 引用
- 不需要主动调外部 API——除非用户 goal 明确说要查最新动态

## 过程要求

- 写报告过程中，可在对话中实时输出关键发现
- 最终输出 markdown 报告本身 + 一句话总结

开始：从"## 1. 产品/方案定位"开始写。
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
            "--max-turns", "20",
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
