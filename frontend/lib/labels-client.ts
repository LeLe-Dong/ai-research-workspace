// Client-safe labels (no React imports, can be used in non-React contexts).

import type { AgentMode } from "./types";

export const AGENT_MODE_KEYS: AgentMode[] = ["mock", "llm", "hermes-researcher"];

export const AGENT_MODE_LABELS: Record<AgentMode, string> = {
  mock: "演示模式",
  llm: "LLM 模型",
  "hermes-researcher": "Hermes 研究员",
};
