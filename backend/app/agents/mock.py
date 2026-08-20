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


# Mapping from TIMELINE_PHASES index → TASK_TREE task index. This binds every
# trace event to a task, so the Console can show per-task runtime logs.
# Phase taxonomy:
#   understand / decompose  → task 0  (requirement)
#   search / read            → tasks 1-3 (research)
#   analyze / derive        → tasks 4-5 (comparison) and 6-7 (evaluation)
#   summarize               → tasks 8-9 (report)
PHASE_TO_TASK = [
    0,  # understand   → requirement
    0,  # decompose    → requirement
    1,  # search       → research (信息收集)
    2,  # read         → research (来源筛选)
    1,  # search       → research (信息收集)
    3,  # read         → research (深度阅读)
    4,  # analyze      → comparison
    2,  # search       → research (来源筛选)
    3,  # read         → research (深度阅读)
    4,  # derive       → comparison
    5,  # analyze      → comparison
    5,  # derive       → comparison
    6,  # analyze      → evaluation
    7,  # derive       → evaluation
    8,  # summarize    → report
    8,  # summarize    → report
    9,  # summarize    → report
    9,  # summarize    → report
    9,  # summarize    → report
    9,  # summarize    → report
]


TIMELINE_PHASES = [
    # (phase, title, detail_summary, kind, trace_payload_factory)
    (
        "understand", "理解研究目标",
        "解析用户意图，识别成功标准与边界条件。",
        "llm_call",
        lambda req: (
            "PROMPT:\n"
            f"  目标: {req.goal}\n"
            f"  约束: {req.constraints or '(无)'}\n"
            f"  深度: {req.depth}  优先级: {req.priority}\n\n"
            "OUTPUT:\n"
            "  - 核心问题: 在当前约束下找出推荐方案\n"
            "  - 成功标准: 4 维度评分 ≥ 7.5\n"
            "  - 排除项: 已淘汰的 1 个方案\n\n"
            "METRICS:\n"
            "  tokens: 384 in / 217 out\n"
            "  latency: 1.42s"
        ),
    ),
    (
        "decompose", "拆解为子问题",
        "将研究目标拆解为 6 个原子子问题。",
        "analysis",
        lambda req: (
            "SUB-QUESTIONS:\n"
            "  1. 当前业界主流做法是什么？\n"
            "  2. 各类方案的核心权衡点？\n"
            "  3. 工程实施的关键风险？\n"
            "  4. 成本与运维投入估算？\n"
            "  5. 团队学习成本与上手周期？\n"
            "  6. 长期演进路径与生态成熟度？\n\n"
            "STRATEGY: parallel_search × 3 then synthesize"
        ),
    ),
    (
        "search", "检索网络：3 个查询",
        "调用搜索 API，分发 3 个并行查询。",
        "search",
        lambda req: (
            "QUERIES:\n"
            f"  Q1: \"{req.goal}\" best practices 2026\n"
            f"  Q2: \"{req.goal}\" comparison vs alternative\n"
            f"  Q3: \"{req.goal}\" production case study\n\n"
            "RESULTS:\n"
            "  Q1: 12 hits (top 5 retained)\n"
            "  Q2:  8 hits (top 4 retained)\n"
            "  Q3:  6 hits (top 3 retained)\n\n"
            "DEDUPED: 11 unique sources"
        ),
    ),
    (
        "read", "读取来源 1/11：arXiv 综述",
        "从 arXiv 抽取 8 条核心论断 + 3 个量化数据点。",
        "fetch",
        lambda req: (
            "URL: https://arxiv.org/abs/2401.12345\n"
            "STATUS: 200 OK (38s)\n"
            "SIZE: 142 KB\n\n"
            "KEY CLAIMS:\n"
            "  1. 在 1000+ 并发下方案 A 的 P99 延迟 < 200ms\n"
            "  2. 方案 B 在弹性伸缩场景下资源利用率高 35%\n"
            "  3. 混合架构的运维成本约为全量重构的 1/3\n"
            "  4. 80% 的受访团队认为渐进式迁移风险更低\n"
            "  ... [共 8 条]\n\n"
            "QUANTITATIVE DATA:\n"
            "  - 性能: 1.2x vs 2.4x vs 3.8x\n"
            "  - 成本: $1.0x vs $3.2x vs $1.8x\n"
            "  - 周期: 1月 vs 6月 vs 3月"
        ),
    ),
    (
        "search", "检索官方文档",
        "拉取 4 个官方项目站点的参考文档。",
        "search",
        lambda req: (
            "SOURCES:\n"
            "  • official-site-a.com/docs (5 pages)\n"
            "  • official-site-b.org/reference (8 pages)\n"
            "  • official-site-c.io/handbook (3 pages)\n"
            "  • github.com/.../wiki (12 pages)\n\n"
            "TOTAL: 28 pages indexed"
        ),
    ),
    (
        "read", "读取来源 5/11：工程博客",
        "捕获真实部署模式与经验教训。",
        "fetch",
        lambda req: (
            "URL: https://eng.blog.company.io/deploying-at-scale\n"
            "STATUS: 200 OK\n\n"
            "KEY POINTS:\n"
            "  - 灰度发布 4 周 → 0 个 P0 故障\n"
            "  - 数据库迁移使用 dual-write 模式，切换 < 5min\n"
            "  - 监控关键指标: p99, error_rate, queue_depth\n"
            "  - 团队: 8 名工程师 / 3 个月完成\n\n"
            "QUOTE:\n"
            "  \"渐进式比一次性重构风险低 70%，但收益也更慢显现。\""
        ),
    ),
    (
        "analyze", "分析量化数据",
        "在 3 个评估框架间归一化指标。",
        "analysis",
        lambda req: (
            "FRAMEWORKS:\n"
            "  • Forrester Wave    (权重 25%)\n"
            "  • Gartner MQ         (权重 35%)\n"
            "  • Internal heuristic (权重 40%)\n\n"
            "NORMALIZED SCORES (1-10):\n"
            "  方案 A: 8.4  方案 B: 6.0  方案 C: 7.5\n\n"
            "DRIFT CHECK:\n"
            "  - 跨框架一致度 92%\n"
            "  - 1 项指标重新校准"
        ),
    ),
    (
        "search", "检索反面观点",
        "为领先方案找可信的反对意见。",
        "search",
        lambda req: (
            "QUERIES:\n"
            "  Q1: \"{goal}\" failure cases\n"
            "  Q2: \"{goal}\" alternatives criticism\n\n"
            "FOUND 2 CREDIBLE DISSENTS:\n"
            "  1. \"Why We Migrated Away from Solution A\" — eng blog\n"
            "  2. \"Solution B Limitations in Production\" — conference talk\n\n"
            "VERDICT: balanced view achieved"
        ),
    ),
    (
        "read", "读取来源 11/11：行业报告",
        "对比 24 个月内的市场份额与采用率曲线。",
        "fetch",
        lambda req: (
            "URL: industry-report-2026.pdf\n"
            "TIMEFRAME: 2024-Q1 → 2026-Q1\n\n"
            "ADOPTION CURVES:\n"
            "  方案 A: 45% → 38%  (-7pp)\n"
            "  方案 B: 18% → 22%  (+4pp)\n"
            "  方案 C: 27% → 35%  (+8pp) ← 增长最快\n\n"
            "GROWTH DRIVERS:\n"
            "  - 方案 C: 工具链成熟 + 学习曲线平缓"
        ),
    ),
    (
        "derive", "推导候选方案",
        "从证据库综合出 3 个候选方案。",
        "analysis",
        lambda req: (
            "CANDIDATES:\n"
            "  A. 渐进式改造 — 保留旧系统，分阶段引入新组件\n"
            "  B. 全量重构   — 完全替换，技术栈现代化\n"
            "  C. 混合架构   — 新旧并存，适配层桥接\n\n"
            "EVIDENCE BASE:\n"
            "  11 sources, 6 dimensions, 4 dissenting opinions"
        ),
    ),
    (
        "analyze", "构建对比矩阵",
        "在 3 个候选方案间映射 8 个评估维度。",
        "analysis",
        lambda req: (
            "DIMENSIONS:\n"
            "  1. 技术可行性\n"
            "  2. 可维护性\n"
            "  3. 可扩展性\n"
            "  4. 实施周期\n"
            "  5. 风险等级\n"
            "  6. 成本投入\n"
            "  7. 团队学习成本\n"
            "  8. 生态成熟度\n\n"
            "MATRIX: 见 comparison-table.md artifact"
        ),
    ),
    (
        "derive", "权衡映射",
        "应用约束权重，识别 2 个关键权衡点。",
        "analysis",
        lambda req: (
            "WEIGHTS:\n"
            "  团队能力: 0.30  预算: 0.25  时间: 0.25  风险偏好: 0.20\n\n"
            "TOP TRADE-OFFS:\n"
            "  1. 性能 vs 复杂度 (方案 B 收益高但团队小)\n"
            "  2. 短期投入 vs 长期收益 (方案 A 短期最低，但 2-3 年后需二次改造)"
        ),
    ),
    (
        "analyze", "估算实施成本",
        "建模工程投入、基础设施成本与时间线。",
        "analysis",
        lambda req: (
            "ENGINEERING:\n"
            "  方案 A: 4 人月  方案 B: 18 人月  方案 C: 9 人月\n\n"
            "INFRA COST (annual):\n"
            "  方案 A: $48K  方案 B: $156K  方案 C: $86K\n\n"
            "TIMELINE:\n"
            "  方案 A: 4 周  方案 B: 20 周  方案 C: 12 周"
        ),
    ),
    (
        "derive", "识别风险",
        "按可能性与影响维度分类 6 个风险。",
        "analysis",
        lambda req: (
            "RISK MATRIX:\n"
            "  H H │            选型错误\n"
            "    M │ 进度延误  团队不足\n"
            "  M L │ 需求变更  故障处理\n"
            "    L │ ──────────────→ 影响\n"
            "      L   M   H\n\n"
            "TOP RISKS:\n"
            "  • 选型错误 (中可能性 / 高影响)\n"
            "  • 团队技能不足 (中 / 高)\n"
            "  • 故障处理 (中 / 高)"
        ),
    ),
    (
        "summarize", "撰写执行摘要",
        "撰写 4 段执行摘要。",
        "llm_call",
        lambda req: (
            "PROMPT:\n"
            "  撰写 4 段执行摘要，包含：背景 / 推荐 / 关键权衡 / 后续\n"
            f"  推荐方案：基于 {req.goal} 的最佳路径\n\n"
            "OUTPUT:\n"
            "  摘要段 1 (背景): ... [128 字]\n"
            "  摘要段 2 (推荐): ... [156 字]\n"
            "  摘要段 3 (权衡): ... [94 字]\n"
            "  摘要段 4 (后续): ... [78 字]\n\n"
            "METRICS:\n"
            "  tokens: 1240 in / 512 out\n"
            "  latency: 3.8s"
        ),
    ),
    (
        "summarize", "组装对比表格",
        "渲染候选方案对比表格。",
        "render",
        lambda req: (
            "OUTPUT: comparison-table.md\n"
            "ROWS: 8  COLUMNS: 3\n"
            "FORMAT: GitHub-flavored markdown\n\n"
            "SEE ARTIFACT: comparison-table.md"
        ),
    ),
    (
        "summarize", "撰写推荐方案",
        "选出推荐方案并附理由。",
        "llm_call",
        lambda req: (
            "PROMPT:\n"
            "  基于矩阵和权衡给出最终推荐\n\n"
            "RECOMMENDATION: 混合架构方案 C\n"
            "RATIONALE:\n"
            "  1. 与当前技术栈匹配度最高\n"
            "  2. 实施风险在可接受范围\n"
            "  3. 长期演进路径清晰\n\n"
            "METRICS:\n"
            "  tokens: 580 in / 198 out\n"
            "  latency: 1.9s"
        ),
    ),
    (
        "summarize", "编译最终报告",
        "组装 12 节研究终稿。",
        "render",
        lambda req: (
            "OUTPUT: final-report.md\n"
            "SECTIONS: 12\n"
            "WORDS: 3,847\n"
            "TABLES: 2\n"
            "MERMAID: 1\n\n"
            "SEE ARTIFACT: final-report.md"
        ),
    ),
    (
        "summarize", "AI 评审启动",
        "评审员开始打分：技术可行性、风险、成本...",
        "llm_call",
        lambda req: (
            "REVIEWER MODEL: hermes-researcher\n"
            "DIMENSIONS: 7\n"
            "  technical_feasibility, maintainability, complexity,\n"
            "  scalability, innovation, risk, cost\n\n"
            "PROMPT: 基于完整报告，从 7 个维度评分"
        ),
    ),
    (
        "summarize", "AI 评审完成",
        "整体评分 8.4/10，已附改进建议。",
        "llm_call",
        lambda req: (
            "SCORES:\n"
            "  technical_feasibility: 8.5\n"
            "  maintainability:        7.5\n"
            "  complexity:            6.5\n"
            "  scalability:           8.0\n"
            "  innovation:            7.5\n"
            "  risk:                  7.0\n"
            "  cost:                  7.5\n"
            "  ──────────────────────\n"
            "  OVERALL:               8.4/10  ✓ 阈值通过\n\n"
            "STRENGTHS:\n"
            "  • 推荐方案与团队能力高度匹配\n"
            "  • 实施路径分阶段可控\n\n"
            "SUGGESTIONS:\n"
            "  • 加强监控指标的覆盖度\n"
            "  • 提前规划回退机制"
        ),
    ),
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
本报告基于对 **{title}** 的系统性研究…
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
        # 1) Task tree — milestones bound to specific tasks
        for idx, (phase, name, desc) in enumerate(TASK_TREE):
            yield AgentEvent(
                phase=phase,
                level="info",
                title=f"[任务 {idx + 1}/{len(TASK_TREE)}] {name}",
                detail=desc,
                task_id=f"task-{idx:02d}",
                task_progress=0,
            )

        # 2) Detailed runtime trace events, each tied to its owning task
        n_events = len(TIMELINE_PHASES)
        per_event = max(self.duration_seconds / n_events, 0.05)
        for idx, (phase, title, summary, kind, payload_fn) in enumerate(TIMELINE_PHASES):
            await asyncio.sleep(per_event)

            # The "summary" event — high-level milestone (phase-level visibility)
            yield AgentEvent(
                phase=phase,
                level="success" if idx == n_events - 1 else "info",
                title=title,
                detail=summary,
                task_id=f"task-{PHASE_TO_TASK[idx]:02d}",
            )

            # The "trace" event — detailed runtime payload (per task)
            yield AgentEvent(
                phase=phase,
                level="info",
                title=f"  ↳ trace: {title}",
                detail=payload_fn(req),
                task_id=f"task-{PHASE_TO_TASK[idx]:02d}",
            )

            # Update task progress in lockstep
            if idx % 2 == 0:
                progress = int(100 * (idx + 1) / n_events)
                yield AgentEvent(
                    phase="progress",
                    level="info",
                    title=f"[进度] {progress}%",
                    detail=f"task-{min(idx // 2, len(TASK_TREE) - 1):02d} 已完成 {progress}%",
                    task_id=f"task-{min(idx // 2, len(TASK_TREE) - 1):02d}",
                    task_progress=progress,
                )

        # 3) Final artifacts
        rec = "混合架构方案"
        overall = 8.4
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
            n_tasks=len(tasks),
        )
        # report task = task-09 (last in TASK_TREE)
        yield AgentEvent(
            phase="summarize",
            level="success",
            title="产物就绪: research-flow.mmd",
            detail="Mermaid 图，分析流程可视化\nKind: mermaid\nBytes: 1.2KB",
            task_id="task-09",
            artifact={"kind": "mermaid", "title": "Research Flow", "content": MERMAID_TEMPLATE},
        )
        yield AgentEvent(
            phase="summarize",
            level="success",
            title="产物就绪: final-report.md",
            detail="完整研究报告\nSections: 12\nWords: 3,847",
            task_id="task-09",
            artifact={"kind": "markdown", "title": "Final Report", "content": md},
        )
        yield AgentEvent(
            phase="summarize",
            level="success",
            title="产物就绪: comparison-table.md",
            detail="候选方案对比矩阵\nRows: 8  Cols: 3",
            task_id="task-09",
            artifact={"kind": "table", "title": "Comparison Table", "content": _render_table()},
        )

        # 4) Reviewer (task-09 again)
        yield AgentEvent(
            phase="review",
            level="success",
            title="评审员完成",
            detail="Overall score 8.4/10\n阈值通过 (>= 7.5)\nStrengths: 3\nSuggestions: 5",
            task_id="task-09",
            artifact={"kind": "review", "title": "Reviewer", "content": ""},
        )


def _render_table() -> str:
    """Render a 3-candidate comparison matrix (mock fallback)."""
    candidates = [
        ("候选 A\n渐进式改造", {"technical_feasibility": 8.5, "maintainability": 7.0, "scalability": 6.5, "innovation": 5.0, "risk": 8.0, "cost": 9.0, "complexity": 8.5}),
        ("候选 B\n全量重构", {"technical_feasibility": 6.0, "maintainability": 8.5, "scalability": 9.0, "innovation": 9.0, "risk": 4.0, "cost": 3.0, "complexity": 4.0}),
        ("候选 C\n混合架构", {"technical_feasibility": 7.5, "maintainability": 7.0, "scalability": 8.0, "innovation": 7.0, "risk": 6.0, "cost": 6.0, "complexity": 6.5}),
    ]
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
            if v >= 8.0:
                cells.append(f"⭐ {v}/10")
            elif v >= 6.0:
                cells.append(f"✓ {v}/10")
            else:
                cells.append(f"⚠ {v}/10")
        rows.append(f"| {dim_labels.get(dim, dim.replace('_', ' ').title())} | " + " | ".join(cells) + " |")
    rows.append("| **综合评分** | **8.5/10** | **6.0/10** | **7.5/10** |")
    rows.append("| **推荐** | 备选 | 高风险/高收益 | ✓ **推荐** |")
    return "\n".join(rows)
