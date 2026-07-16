/**
 * Smart expansion - heuristic-based text enhancement.
 * No LLM needed for common cases. Falls back to basic cleanup if no patterns match.
 */

const EXPANSION_PATTERNS: { match: RegExp; expand: (m: RegExpMatchArray) => string }[] = [
  // "对比 A 和 B" → "对比 A 和 B 的差异、各自优缺点、适用场景"
  {
    match: /(?:对比|比较|vs\.?)\s*(.+?)\s*(?:和|与|vs\.?)\s*(.+?)(?:[，。]|$)/i,
    expand: (m) =>
      `对比 ${m[1].trim()} 和 ${m[2].trim()}：\n\n1. 核心差异：架构设计、技术栈、适用场景；\n2. 性能对比：吞吐量、延迟、资源消耗；\n3. 运维成本：学习曲线、社区活跃度、文档质量；\n4. 推荐：基于 {团队规模} 和 {业务场景} 的具体推荐及理由。`,
  },
  // "如何/怎么" questions
  {
    match: /(?:如何|怎么)\s*(.+?)(?:[?？。]|$)/,
    expand: (m) =>
      `如何 ${m[1].trim()}：\n\n1. 问题定义：{当前痛点}；\n2. 解决方案候选：{列出 2-3 个方案}；\n3. 各方案的优缺点对比；\n4. 实施步骤和风险。`,
  },
  // "为什么" questions
  {
    match: /(?:为什么|为啥)\s*(.+?)(?:[?？。]|$)/,
    expand: (m) =>
      `为什么 ${m[1].trim()}：\n\n1. 现象描述：{具体表现}；\n2. 可能原因：{列出 3-5 个可能}；\n3. 验证方法：{如何确认根因}；\n4. 解决方案：{针对每个可能原因的应对}。`,
  },
  // "选择/选哪个" questions
  {
    match: /(?:选择|选哪个|用哪个)\s*(.+?)(?:[?？。]|$)/,
    expand: (m) =>
      `选择 ${m[1].trim()}：\n\n1. 候选清单：{列出 3-5 个主流选项}；\n2. 评估维度：性能/成本/易用性/社区/长期维护；\n3. 各选项评分对比；\n4. 推荐：基于 {具体场景} 的最佳选择。`,
  },
];

/**
 * Try to expand a short goal into a more detailed research question.
 * Returns the expanded text, or the original if no patterns match.
 */
export function smartExpandGoal(input: string): string {
  if (!input || input.length < 5) return input;
  const trimmed = input.trim();

  // Try each pattern
  for (const { match, expand } of EXPANSION_PATTERNS) {
    const m = trimmed.match(match);
    if (m) {
      return expand(m);
    }
  }

  // Generic expansion: just add structure
  return `${trimmed}\n\n请从以下角度分析：\n1. 背景与现状\n2. 关键问题或挑战\n3. 可能的解决方案\n4. 实施建议`;
}

/**
 * Add a structural skeleton to a goal that lacks structure.
 * Returns the enhanced version with bullet points.
 */
export function addStructure(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return trimmed;

  // If it already has structure (bullets, numbers, line breaks), don't touch
  if (/[\n•\-]/.test(trimmed) || /\d\./.test(trimmed)) {
    return trimmed;
  }

  return `${trimmed}\n\n关键考虑：\n• 适用场景：\n• 核心优势：\n• 主要挑战：\n• 推荐理由：`;
}

/**
 * Sanity check: does the goal look detailed enough?
 */
export function isGoalDetailed(goal: string): { ok: boolean; reason?: string } {
  if (!goal || goal.trim().length < 20) {
    return { ok: false, reason: "目标太短（< 20 字符），LLM 难以理解" };
  }
  if (goal.trim().length < 50) {
    return { ok: false, reason: "目标较短（< 50 字符），建议补充更多上下文" };
  }
  if (!/[。！？.!?\n]/.test(goal)) {
    return { ok: false, reason: "目标缺少结构，建议用句号或换行分段" };
  }
  return { ok: true };
}
