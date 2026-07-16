export type Priority = "low" | "medium" | "high";
export type Depth = "quick" | "standard" | "deep";
export type ResearchStatus = "pending" | "running" | "completed" | "failed";

export interface DashboardStats {
  total_researches: number;
  completed: number;
  running: number;
  today_completed: number;
  average_score: number;
}

export interface RecentResearch {
  id: string;
  title: string;
  status: ResearchStatus;
  priority: Priority;
  depth: Depth;
  score: number | null;
  updated_at: string;
  tags?: Tag[];
  error_message?: string | null;
}

export interface PopularKnowledge {
  id: string;
  research_id: string;
  title: string;
  excerpt: string;
  tags: string[];
  score: number;
  updated_at: string;
}

export interface AgentStatus {
  engine: string;
  mode: string;
  version: string;
  online: boolean;
  last_active: string | null;
}

export interface DashboardData {
  stats: DashboardStats;
  recent: RecentResearch[];
  popular: PopularKnowledge[];
  agent: AgentStatus;
}

export interface ResearchCreate {
  title: string;
  goal: string;
  constraints?: string;
  expected_output?: string;
  depth?: Depth;
  priority?: Priority;
  estimated_cost?: number;
}

export interface ResearchSummary extends RecentResearch {}

export interface ResearchDetail {
  id: string;
  title: string;
  goal: string;
  constraints: string;
  expected_output: string;
  depth: Depth;
  priority: Priority;
  estimated_cost: number;
  status: ResearchStatus;
  created_at: string;
  updated_at: string;
  tags?: Tag[];
  error_message?: string | null;
}

export interface TaskNode {
  id: string;
  parent_id: string | null;
  name: string;
  phase: string;
  status: "pending" | "running" | "done" | "failed";
  progress: number;
  order_index: number;
}

export interface TimelineEventOut {
  id: string;
  ts: string;
  phase: string;
  level: "info" | "warn" | "error" | "success";
  title: string;
  detail: string;
  sequence: number;
}

export interface ArtifactOut {
  id: string;
  kind: string;
  title: string;
  content: string;
  version: number;
  created_at: string;
}

export interface ReviewOut {
  overall_score: number;
  dimensions: Record<string, number>;
  strengths: string;
  weaknesses: string;
  suggestions: string;
  threshold: number;
}
export type AgentMode = "mock" | "stepfun" | "hermes-researcher";

export interface HistoryVersion {
  id: string;
  version: number;
  title: string;
  status: string;
  created_at: string;
  created_by: string | null;
  commit_message: string | null;
  parent_version: number | null;
}

export interface HistoryDiff {
  research_id: string;
  v1: number;
  v2: number;
  field_diffs: Array<{ field: string; v1: string; v2: string }>;
  report_diffs: Array<{ field: string; changed: boolean; v1_len: number; v2_len: number }>;
  changed: boolean;
}

export interface ForkResponse {
  id: string;
  title: string;
  status: string;
  forked_from: string;
}

export interface Tag {
  id: string;
  name: string;
  color: string;
  count?: number;
}
