import { api } from "@/lib/api";

export interface ReportSection {
  executive_summary: string | null;
  research_flow_diagram: string | null;
  comparison_table: string | null;
}

export interface ReportReview {
  overall_score: number | null;
  dimensions: Record<string, number>;
  // Legacy string fields (kept for backwards compat with old reviews)
  strengths: string | string[];
  weaknesses: string | string[];
  suggestions: string | string[];
  // New structured fields (Phase 25)
  verdict?: string;
  strengths_list?: string[];
  weaknesses_list?: string[];
  improvements?: string[];
  critical_questions?: string[];
  next_steps?: string[];
  threshold: number;
}

export interface Report {
  research: {
    id: string;
    title: string;
    goal: string;
    constraints: string;
    expected_output: string;
    depth: string;
    priority: string;
    status: string;
    created_at: string;
    updated_at: string;
  };
  sections: ReportSection;
  full_report?: string | null;
  review: ReportReview | null;
}

export interface CompletedResearch {
  id: string;
  title: string;
  goal: string;
  depth: string;
  priority: string;
  score: number | null;
  created_at: string;
  updated_at: string;
}

export const reportApi = {
  get: (id: string) => api.get<Report>(`/api/v1/researches/${id}/report`),
  listCompleted: () => api.get<CompletedResearch[]>("/api/v1/completed-researches"),
};
