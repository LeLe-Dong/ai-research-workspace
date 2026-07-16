// Client-safe labels (no React imports, can be used in non-React contexts).

import type { AgentMode } from "./types";

export const AGENT_MODE_KEYS: AgentMode[] = ["mock", "stepfun", "hermes-researcher"];

export const AGENT_MODE_LABELS: Record<AgentMode, string> = {
  mock: "演示模式",
  stepfun: "Stepfun LLM",
  "hermes-researcher": "Hermes 研究员",
};
