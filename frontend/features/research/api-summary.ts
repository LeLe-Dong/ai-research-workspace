/**
 * /summary endpoint types + API wrapper.
 *
 * Single round-trip aggregated view of a research's execution state
 * (replaces the 7-call pattern of researches + tasks + timeline +
 * artifacts + report + review + versions).
 */

import { api } from "@/lib/api";

export interface ReviewSummary {
  overall_score: number;
  dimensions: Record<string, number>;
  strengths: string;
  weaknesses: string;
  suggestions: string;
  threshold: number;
}

export interface ArtifactSummary {
  kind: string;
  title: string;
  version: number;
  size_bytes: number;
}

export interface ResearchProgress {
  id: string;
  title: string;
  status: string;
  priority: string;
  depth: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  duration_sec: number | null;

  // Progress counters
  progress_tasks_done: number;
  progress_tasks_total: number;
  progress_tasks_pct: number; // 0..100
  progress_timeline_events: number;
  progress_timeline_first: string | null;
  progress_timeline_last: string | null;
  progress_timeline_gap_sec: number | null;

  // Score + review
  score: number | null;
  review: ReviewSummary | null;

  // Content
  artifacts: ArtifactSummary[];
  report_length_chars: number;
  versions_count: number;

  // Coverage gaps — human-readable list of what's missing/incomplete
  coverage_gaps: string[];
}

export const summaryApi = {
  get: (id: string) =>
    api.get<ResearchProgress>(`/api/v1/researches/${id}/summary`),
};