/**
 * Research templates - pre-filled forms for common scenarios.
 * Click a template to populate the form fields.
 */
export interface ResearchTemplate {
  id: string;
  category: string;
  title: string;
  goal: string;
  constraints?: string;
  expected_output?: string;
  depth?: "quick" | "standard" | "deep";
  priority?: "low" | "medium" | "high";
  icon: string;
}

export const TEMPLATES: ResearchTemplate[] = [
  {
    id: "tech-selection",
    category: "选型对比",
    icon: "🔍",
    title: "选型对比：评估多个技术选项",
    goal: "评估 {技术A} 和 {技术B} 在 {具体场景} 下的表现，包括：性能、可扩展性、学习曲线、社区活跃度、运维成本。需要给出明确的推荐和理由。",
    constraints: "团队规模：{N} 人；技术栈：{已有栈}；预算：{预算}；时间：{周期}。",
    expected_output: "1) 详细对比矩阵；2) 推荐方案及理由；3) 90 天落地计划；4) 风险点与缓解措施。",
    depth: "standard",
    priority: "high",
  },
  {
    id: "tech-evolution",
    category: "技术演进",
    icon: "🔄",
    title: "技术演进：从 X 到 Y 的迁移方案",
    goal: "研究从 {当前技术/架构} 迁移到 {目标技术/架构} 的可行路径，分析改造成本、风险、业务影响。给出渐进式（strangler）和一次性（big bang）两种方案的对比。",
    constraints: "不能停机；不影响线上业务；3 人团队；3 个月内完成。",
    expected_output: "1) 两种迁移方案对比；2) 分阶段实施计划；3) 关键风险与回滚方案；4) 资源与时间估算。",
    depth: "deep",
    priority: "high",
  },
  {
    id: "tool-evaluation",
    category: "工具评估",
    icon: "🛠️",
    title: "工具评估：评估工具/库/框架",
    goal: "评估 {工具/库名} 用于 {具体用例} 的可行性，对比同类替代方案。重点关注：API 设计、性能、稳定性、文档质量、商业支持、长期维护风险。",
    expected_output: "1) 工具能力评估；2) 与同类对比；3) PoC 建议；4) 风险评估。",
    depth: "quick",
    priority: "medium",
  },
  {
    id: "architecture-decision",
    category: "架构决策",
    icon: "🏛️",
    title: "架构决策：{系统名} 应该怎么设计？",
    goal: "为 {系统名} 设计架构方案。需要考虑：功能需求、非功能需求（性能/可用性/扩展性）、约束条件（成本/团队/合规）。给出至少 2 个候选方案 + 推荐。",
    constraints: "QPS 峰值 {N}；存储量 {PB/TB}；可用性要求 {99.9/99.99%}；团队 {N} 人。",
    expected_output: "1) 需求分析；2) 至少 2 个架构方案；3) 推荐方案 + 理由；4) 关键模块设计。",
    depth: "deep",
    priority: "high",
  },
  {
    id: "best-practices",
    category: "最佳实践",
    icon: "✨",
    title: "最佳实践：{技术/场景} 怎么做？",
    goal: "研究 {技术/场景} 的行业最佳实践，收集 Top 5 团队的做法，提炼出可复用的模式与反模式。",
    expected_output: "1) 行业领先案例；2) 核心模式与反模式；3) 落地建议。",
    depth: "standard",
    priority: "medium",
  },
  {
    id: "troubleshooting",
    category: "问题诊断",
    icon: "🔧",
    title: "问题诊断：{具体问题} 怎么解决？",
    goal: "诊断并解决 {具体问题描述}。分析根因，评估各种解决方案的成本/风险，给出推荐修复方案和预防措施。",
    expected_output: "1) 根因分析；2) 至少 2 个修复方案；3) 推荐方案；4) 长期预防措施。",
    depth: "quick",
    priority: "high",
  },
  {
    id: "ai-llm",
    category: "AI/LLM",
    icon: "🤖",
    title: "AI 选型：评估 LLM/Agent 框架",
    goal: "评估 {LLM/Agent 框架名} 用于 {场景} 的可行性，对比同类方案。关注：能力边界、API 易用性、成本、可控性、企业级特性。",
    expected_output: "1) 能力对比；2) 成本估算；3) PoC 计划；4) 集成方案。",
    depth: "standard",
    priority: "medium",
  },
  {
    id: "data-decision",
    category: "数据决策",
    icon: "📊",
    title: "数据决策：{指标/问题} 怎么提升？",
    goal: "分析 {业务指标/数据问题} 现状，识别关键影响因素，给出可执行的优化方案和预期效果。",
    constraints: "当前值：{X}；目标值：{Y}；时间：{N} 个月。",
    expected_output: "1) 现状分析；2) 影响因素排序；3) 优化方案；4) ROI 估算。",
    depth: "standard",
    priority: "medium",
  },
];
