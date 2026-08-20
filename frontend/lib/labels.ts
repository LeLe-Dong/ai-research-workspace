// 中文显示层：保留英文 enum 内部值，对外显示中文。

import type { Priority, Depth, ResearchStatus, AgentMode } from "./types";

export const STATUS_LABELS: Record<ResearchStatus, string> = {
  pending: "待开始",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
};

export const PRIORITY_LABELS: Record<Priority, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

export const DEPTH_LABELS: Record<Depth, { label: string; desc: string }> = {
  quick: { label: "快速", desc: "3 个信息源，约 5 分钟" },
  standard: { label: "标准", desc: "12 个信息源，约 15 分钟" },
  deep: { label: "深度", desc: "30 个信息源，约 60 分钟" },
};

export const AGENT_MODE_LABELS: Record<AgentMode, string> = {
  mock: "演示模式",
  llm: "LLM 模型",
  "hermes-researcher": "Hermes 研究员",
};

export const KIND_LABELS: Record<string, string> = {
  mermaid: "研究流程图",
  markdown: "研究报告",
  table: "对比表",
  review: "评审报告",
};

// 通用 UI 文案
export const UI = {
  appName: "AI 预研工作台",
  appSubtitle: "企业级 AI 研究平台",

  nav: {
    dashboard: "工作台",
    research: "研究",
    knowledge: "知识库",
    history: "历史",
    settings: "设置",
    newResearch: "新建研究",
  },

  agent: {
    statusOnline: "在线",
    statusMock: "演示",
    statusOffline: "离线",
    versionLabel: "版本",
    lastActiveLabel: "最近活跃",
  },

  dashboard: {
    title: "工作台",
    subtitle: "研究项目、智能体状态、最近活动总览",
    totalResearches: "研究总数",
    completedToday: "今日完成",
    running: "执行中",
    averageScore: "平均评分",
    recentResearches: "最近研究",
    popularKnowledge: "热门知识",
    viewAll: "查看全部",
    noResearches: "暂无研究",
    noKnowledge: "暂无知识库",
    pinnedProjects: "置顶项目",
    quickStart: "快速开始",
  },

  research: {
    title: "研究",
    listTitle: "所有研究",
    newTitle: "新建研究",
    detailTitle: "研究详情",
    formGoal: "研究目标",
    formTitle: "研究标题",
    formConstraints: "约束条件",
    formExpected: "预期输出",
    formDepth: "Depth",
    formPriority: "Priority",
    formCost: "预估成本",
    depthSection: "研究配置",
    constraintsSection: "约束与输出",
    goalSection: "研究目标",
    start: "开始研究",
    startHint: "MockAgentClient 将在约 4 秒内生成 5 阶段计划 + 20 个时间线事件 + 3 个产出物",
    back: "返回",
    noHistory: "暂无研究",
    createHint: "点击「新建研究」开始第一个研究项目",
    fields: {
      title: "标题",
      goal: "目标",
      constraints: "约束",
      expected: "预期输出",
      depth: "深度",
      priority: "Priority",
      cost: "成本",
    },
    deleteConfirm: "确认删除「{title}」？此操作不可恢复。",
    execution: "执行",
    viewReport: "查看报告",
    runAgain: "重新执行",
    running: "执行中...",
  },

  execution: {
    title: "执行",
    taskTree: "任务树",
    timeline: "时间线",
    liveArtifact: "实时产物",
    console: "控制台",
    waiting: "等待智能体...",
    progress: "进度",
    eventsCount: "事件数",
    elapsed: "耗时",
    tokens: "Tokens",
    errors: "错误",
  },

  report: {
    title: "研究报告",
    finalReport: "最终研究报告",
    passedThreshold: "通过阈值",
    belowThreshold: "未达阈值",
    downloadMarkdown: "下载 Markdown",
    downloadMermaid: "下载 Mermaid",
    sections: {
      summary: "执行摘要",
      diagram: "研究流程",
      compare: "对比分析",
      review: "智能评审",
    },
    strengths: "优势",
    weaknesses: "不足",
    suggestions: "建议",
    reviewerNote: "评审备注",
    noReport: "暂无报告",
    reviewFailedFallback: "评审失败时使用的默认评分",
    fallbackBanner: "智能体在合成阶段遇到 LLM 错误。以下内容由前置阶段直接生成。",
    reviewerFailedFallback: "评审不可用，使用默认评分。",
  },

  knowledge: {
    title: "知识库",
    subtitle: "所有已完成的研报，可搜索可复用",
    archived: "归档",
    searchPlaceholder: "搜索归档研究...",
    noArchived: "暂无归档研究",
    completeToPopulate: "完成一项研究即可填充此视图",
    backToKnowledge: "返回知识库",
    loadingArchived: "加载归档报告...",
  },

  history: {
    title: "历史",
    subtitle: "研究项目的版本记录。MVP 显示一行一研究；v1.3 将增加 diff / 回滚 / fork 功能。",
    runs: "次运行",
    noHistory: "暂无历史",
    backToHistory: "返回历史",
    loading: "加载历史运行...",
    versionLabel: "版本",
  },

  settings: {
    title: "设置",
    subtitle: "工作区与智能体配置",
  },

  error: {
    loadFailed: "加载失败",
    serverDown: "请确认后端服务运行于端口 8003",
  },
};


// Review dimension labels (Chinese)
export const REVIEW_DIMENSION_LABELS: Record<string, string> = {
  technical_feasibility: "技术可行性",
  maintainability: "可维护性",
  scalability: "可扩展性",
  innovation: "创新性",
  risk: "风险等级",
  cost: "成本投入",
  complexity: "复杂度",
  time_to_value: "实施速度",
  ecosystem_maturity: "生态成熟度",
};
