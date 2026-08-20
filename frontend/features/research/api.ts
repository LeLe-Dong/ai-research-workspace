import { api, API_BASE } from "@/lib/api";
import type { ResearchCreate, ResearchDetail, ResearchSummary } from "@/lib/types";

export const researchApi = {
  list: (params?: { tag?: string; q?: string }) => api.get<ResearchSummary[]>("/api/v1/researches", { params }),
  expandGoal: (goal: string) => api.post<{
    original: string;
    expanded: string;
    model: string;
    cached: boolean;
    tokens_used: number | null;
  }>("/api/v1/expand/goal", { goal }),
  get: (id: string) => api.get<ResearchDetail>(`/api/v1/researches/${id}`),
  create: (body: ResearchCreate) =>
    api.post<ResearchDetail>("/api/v1/researches", body),
  remove: (id: string) =>
    fetch(`${API_BASE}/api/v1/researches/${id}`, {
      method: "DELETE",
    }).then((r) => { if (!r.ok) throw new Error(`${r.status}`); }),
};
