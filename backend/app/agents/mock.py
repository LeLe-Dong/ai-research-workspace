import asyncio
import random
from datetime import datetime

from app.agents.base import AgentClient, AgentEvent, ResearchRequest


# A realistic-sounding scripted storyline. Reused across runs for stable demo.
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


TIMELINE_PHASES = [
    ("understand", "Understanding the research goal", "Parsing the user's intent and identifying success criteria."),
    ("decompose", "Decomposing into sub-questions", "Breaking the goal into 6 atomic research questions."),
    ("search", "Searching external sources", "Querying 12 web sources and 3 internal knowledge bases."),
    ("read", "Reading source 1/12: arXiv survey", "Extracted 8 key claims and 3 quantitative data points."),
    ("search", "Searching official documentation", "Pulled reference docs from 4 official project sites."),
    ("read", "Reading source 5/12: engineering blog", "Captured real-world deployment patterns and lessons learned."),
    ("analyze", "Analyzing quantitative data", "Normalized metrics across 3 different evaluation frameworks."),
    ("search", "Searching for counter-arguments", "Found 2 credible dissenting positions for the leading solution."),
    ("read", "Reading source 11/12: industry report", "Compared market share and adoption curves over 24 months."),
    ("derive", "Deriving candidate solutions", "Synthesized 3 candidate approaches from the evidence base."),
    ("analyze", "Building comparison matrix", "Mapped 8 evaluation dimensions across the 3 candidates."),
    ("derive", "Weighing trade-offs", "Applied constraint weights; surfaced 2 critical trade-offs."),
    ("analyze", "Estimating implementation cost", "Modeled engineering effort, infra cost, and timeline."),
    ("derive", "Identifying risks", "Categorized 6 risks by likelihood and impact."),
    ("summarize", "Drafting executive summary", "Composed the 4-paragraph executive summary."),
    ("summarize", "Composing comparison table", "Rendered the candidate comparison table."),
    ("summarize", "Writing recommendation", "Selected the recommended solution with rationale."),
    ("summarize", "Compiling final report", "Assembled 10-section final research report."),
    ("summarize", "Reviewer evaluation started", "Reviewer is scoring technical feasibility, risk, cost, ..."),
    ("summarize", "Reviewer completed", "Overall score: 8.4/10. Suggestions attached."),
]


MERMAID_TEMPLATE = """graph TD
    A[研究目标] --> B[需求分析]
    B --> C[信息收集]
    B --> D[权衡发现]
    C --> E[对比矩阵]
    D --> E
    E --> F[推荐方案]
    E --> G[风险登记]
    F --> H[实施计划]
    G --> H
    H --> I[最终报告]

    style A fill:#1e40af,stroke:#1e3a8a,color:#fff
    style F fill:#059669,stroke:#047857,color:#fff
    style H fill:#7c3aed,stroke:#5b21b6,color:#fff
    style I fill:#ea580c,stroke:#c2410c,color:#fff
"""


MARKDOWN_TEMPLATE = """# {title}

> 研究目标：{goal}
> 约束：{constraints}

## 1. Executive Summary

本报告基于对 **{title}** 的系统性研究，整合了从技术文档、行业报告、社区讨论和实践案例中提取的关键发现。

研究目标的核心问题是：**{goal_short}**

经分析，**{rec}** 方案在综合评分（{score:.1f}/10）上表现最优，能够在技术可行性、成本投入、运维风险和实施周期四个维度上取得最佳平衡。

预期的业务影响包括：
- 降低 30-50% 的运维成本
- 提升 2-5 倍的扩展能力
- 缩短 60% 的新功能上线时间

## 2. 背景与现状

### 2.1 为什么这个问题现在重要

{title} 是当前技术决策的关键议题，主要驱动因素包括：
- 行业最佳实践在过去 12-18 个月发生了显著变化
- 新的工具/框架已经成熟到生产可用阶段
- 既有方案的痛点已经被广泛记录

### 2.2 当前业界主流做法

目前业内主要采用以下三种思路：
- **传统方案**：以稳定为主，迭代慢但风险低
- **新兴方案**：激进创新，收益高但风险大
- **混合方案**：折中路线，平衡收益与风险

## 3. 详细需求分析

基于研究目标，整理出以下核心需求：

**必须满足（Must-have）**：
- 性能：支持 1000+ 并发用户，P99 延迟 < 500ms
- 可靠性：99.9% 可用性 SLA
- 安全性：通过企业级安全审计
- 可维护性：团队（5-10 人）能在 1 个月内接手

**最好满足（Nice-to-have）**：
- 水平扩展能力
- 生态成熟度（文档、库、社区）
- 未来 3 年的技术演进路径

## 4. 候选方案详解

### 候选方案 A — 渐进式改造
**核心思路**：保留现有系统，分阶段引入新组件

- **优势**：风险可控、团队学习曲线平缓、可灰度发布
- **劣势**：长期成本可能更高、技术债务累积、新功能受限

### 候选方案 B — 全量重构
**核心思路**：完全替换现有系统

- **优势**：架构清晰、技术栈现代化、长期收益大
- **劣势**：初期投入大、风险高、需要专职团队

### 候选方案 C — 混合架构
**核心思路**：新系统与旧系统并存，通过适配层桥接

- **优势**：灵活度高、可逐步迁移、风险分散
- **劣势**：架构复杂度增加、运维成本上升

## 5. 多维度对比矩阵

| 评估维度 | 候选 A | 候选 B | 候选 C |
| --- | --- | --- | --- |
| 技术可行性 | 8.5/10 | 6.0/10 | 7.5/10 |
| 可维护性 | 7.0/10 | 8.5/10 | 7.0/10 |
| 可扩展性 | 6.5/10 | 9.0/10 | 8.0/10 |
| 实施周期 | 9.0/10 (快) | 4.0/10 (慢) | 6.5/10 |
| 风险等级 | 低 | 高 | 中 |
| 成本投入 | 1.0x | 3.2x | 1.8x |
| 团队学习成本 | 1.0x | 2.5x | 1.5x |
| 生态成熟度 | 高 | 中 | 高 |

## 6. 关键权衡分析

在选择 **{rec}** 之前，需要重点考虑以下权衡：

**性能 vs 复杂度**：候选 B 性能最优但复杂度也最高。对于 5-10 人的团队，候选 C 提供了更可控的复杂度。

**短期投入 vs 长期收益**：候选 A 短期投入最低但 2-3 年后可能需要二次改造。候选 C 提供了更平滑的演进路径。

**自主可控 vs 依赖生态**：候选 A/C 依赖成熟生态，候选 B 自主性更强但需要自建更多能力。

## 7. 推荐方案

**{rec}** 是基于本研究的综合推荐。

**核心理由**：
1. 与团队当前技术栈匹配度最高
2. 实施风险在可接受范围内
3. 长期演进路径清晰

**用户需要在决策前明确的 5 个关键点**：
1. 团队的工程能力评估（5/10 vs 8/10 决定了推荐方向）
2. 业务增长预期（10x vs 100x 影响技术选型）
3. 预算约束（影响方案 B 的可行性）
4. 既有系统重构的紧迫性
5. 数据迁移的难度

## 8. 实施计划

### 阶段 1（第 1-4 周）：评估与设计
- 详细技术选型对比
- 原型系统搭建（PoC）
- 团队培训启动
- **交付物**：可行性报告 + PoC 演示

### 阶段 2（第 5-10 周）：核心功能实现
- 主体架构搭建
- 核心数据模型设计
- 关键功能模块开发
- **交付物**：MVP 版本

### 阶段 3（第 11-16 周）：功能完善
- 边缘场景处理
- 性能优化
- 安全加固
- **交付物**：生产就绪版本

### 阶段 4（第 17-20 周）：上线与优化
- 灰度发布
- 监控告警
- 运维手册
- **交付物**：生产上线

## 9. 风险分析与缓解

| 风险 | 可能性 | 影响 | 缓解策略 |
| --- | --- | --- | --- |
| 技术风险：选型错误 | 中 | 高 | 先做 PoC 验证；预留回退方案 |
| 进度风险：工期延误 | 中 | 中 | 采用敏捷迭代；每周 review |
| 团队风险：技能不足 | 中 | 高 | 提前培训；外部专家支持 |
| 业务风险：需求变更 | 高 | 中 | 模块化设计；接口稳定优先 |
| 运维风险：故障处理 | 中 | 高 | 完善监控；故障演练 |

**残余风险**：即使采用推荐方案，仍有 10-20% 的概率需要在 2 年内进行二次调整。建议每 6 个月重新评估技术选型。

## 10. 评审评分

详细评分见右侧「AI 评审」面板的多维雷达图，包括：
- 技术可行性、维护成本、可扩展性、创新性、风险等级、成本投入

## 11. 决策检查清单

实施前需确认以下事项：

- [ ] 团队已评估当前技术债务
- [ ] 业务方已确认 12 个月路线图
- [ ] 预算已通过财务审批
- [ ] 法律/合规已确认无障碍
- [ ] 运维团队已介入设计评审

## 12. 后续行动

### 立即可做（本周）
- [ ] 组建 3-5 人评估小组
- [ ] 启动 PoC 准备工作
- [ ] 约外部专家咨询

### 短期（1 个月内）
- [ ] 完成技术选型对比文档
- [ ] 提交 PoC 计划
- [ ] 启动团队培训

### 中期（3 个月内）
- [ ] 完成 MVP 开发
- [ ] 内部验收测试
- [ ] 准备生产部署

---
*本报告由 AI Research Workspace 自动生成。基于 {n_sources} 个资料源、{n_tasks} 个分析任务和 6 维评审。*
"""


REVIEW_DIMENSIONS = {
    "technical_feasibility": 8.5,
    "maintainability": 7.5,
    "complexity": 6.5,
    "scalability": 8.0,
    "innovation": 7.5,
    "risk": 7.0,
    "cost": 7.5,
}


class MockAgentClient(AgentClient):
    """MVP-only deterministic scripted client."""

    def __init__(self, duration_seconds: float = 4.0) -> None:
        self.duration_seconds = duration_seconds

    async def run_research(self, req: ResearchRequest):
        # 1) Emit task tree quickly
        for idx, (phase, name, desc) in enumerate(TASK_TREE):
            yield AgentEvent(
                phase=phase,
                level="info",
                title=f"Task {idx + 1}/{len(TASK_TREE)}: {name}",
                detail=desc,
                task_id=f"task-{idx:02d}",
                task_progress=0,
            )

        # 2) Timeline events
        n_events = len(TIMELINE_PHASES)
        per_event = max(self.duration_seconds / n_events, 0.05)
        for idx, (phase, title, detail) in enumerate(TIMELINE_PHASES):
            await asyncio.sleep(per_event)
            yield AgentEvent(
                phase=phase,
                level="success" if idx == n_events - 1 else "info",
                title=title,
                detail=detail,
            )
            # Update task progress in lockstep
            if idx % 2 == 0:
                progress = int(100 * (idx + 1) / n_events)
                yield AgentEvent(
                    phase="progress",
                    level="info",
                    title=f"Progress {progress}%",
                    detail="",
                    task_id=f"task-{min(idx // 2, len(TASK_TREE) - 1):02d}",
                    task_progress=progress,
                )

        # 3) Final artifacts
        # Compute recommended option + overall score for the template
        rec = "混合架构方案"  # 模板推荐 - real LLM will vary this
        overall = 8.4  # 模板分数 - real LLM will compute this
        tasks = TASK_TREE
        artifacts = ["research-flow.mmd", "final-report.md", "comparison-table.md"]
        md = MARKDOWN_TEMPLATE.format(
            title=req.title,
            goal=req.goal,
            goal_short=req.goal[:60] + ("..." if len(req.goal) > 60 else ""),
            constraints=req.constraints or "(无特定约束)",
            rec=rec,
            score=overall,
            n_sources=len(artifacts) + 3,
            n_tasks=len(tasks)
        )
        yield AgentEvent(
            phase="summarize",
            level="success",
            title="Artifact ready: research-flow.mmd",
            detail="Mermaid graph of the analysis flow",
            artifact={"kind": "mermaid", "title": "Research Flow", "content": MERMAID_TEMPLATE},
        )
        yield AgentEvent(
            phase="summarize",
            level="success",
            title="Artifact ready: final-report.md",
            detail="Full research report with 10 sections",
            artifact={"kind": "markdown", "title": "Final Report", "content": md},
        )
        yield AgentEvent(
            phase="summarize",
            level="success",
            title="Artifact ready: comparison-table.md",
            detail="Candidate comparison matrix",
            artifact={"kind": "table", "title": "Comparison Table", "content": _render_table()},
        )

        # 4) Reviewer
        yield AgentEvent(
            phase="review",
            level="success",
            title="Reviewer finished",
            detail="Overall score 8.4/10",
            artifact={"kind": "review", "title": "Reviewer", "content": ""},
        )


def _render_table() -> str:
    """Render a 3-candidate comparison matrix (mock fallback).

    Each candidate gets a score per dimension. Candidate names match the report.
    """
    candidates = [
        ("候选 A\n渐进式改造", {"technical_feasibility": 8.5, "maintainability": 7.0, "scalability": 6.5, "innovation": 5.0, "risk": 8.0, "cost": 9.0, "complexity": 8.5}),
        ("候选 B\n全量重构", {"technical_feasibility": 6.0, "maintainability": 8.5, "scalability": 9.0, "innovation": 9.0, "risk": 4.0, "cost": 3.0, "complexity": 4.0}),
        ("候选 C\n混合架构", {"technical_feasibility": 7.5, "maintainability": 7.0, "scalability": 8.0, "innovation": 7.0, "risk": 6.0, "cost": 6.0, "complexity": 6.5}),
    ]
    # Table header
    rows = [
        "| 评估维度 | " + " | ".join(name for name, _ in candidates) + " |",
        "| --- |" + " --- |" * len(candidates),
    ]
    dim_labels = {
        "technical_feasibility": "技术可行性",
        "maintainability": "可维护性",
        "scalability": "可扩展性",
        "innovation": "创新性",
        "risk": "风险控制 (越高越好)",
        "cost": "成本效益 (越高越好)",
        "complexity": "简单度 (越高越简单)",
    }
    for dim, _ in candidates[0][1].items():
        cells = []
        for _, scores in candidates:
            v = scores[dim]
            # Visual: >= 8.0 = ⭐, >= 6.0 = ✓, < 6.0 = ⚠
            if v >= 8.0:
                cells.append(f"⭐ {v}/10")
            elif v >= 6.0:
                cells.append(f"✓ {v}/10")
            else:
                cells.append(f"⚠ {v}/10")
        rows.append(f"| {dim_labels.get(dim, dim.replace('_', ' ').title())} | " + " | ".join(cells) + " |")
    # Summary row
    rows.append("| **综合评分** | **8.5/10** | **6.0/10** | **7.5/10** |")
    rows.append("| **推荐** | 备选 | 高风险/高收益 | ✓ **推荐** |")
    return "\n".join(rows)

