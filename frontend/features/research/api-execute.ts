import { api, API_BASE } from "@/lib/api";
import type { TaskNode, TimelineEventOut, ArtifactOut, ReviewOut } from "@/lib/types";

export const executeApi = {
  start: (id: string) =>
    fetch(`${API_BASE}/api/v1/researches/${id}/start`, {
      method: "POST",
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    }),
  tasks: (id: string) => api.get<TaskNode[]>(`/api/v1/researches/${id}/tasks`),
  timeline: (id: string, since = 0) =>
    api.get<TimelineEventOut[]>(`/api/v1/researches/${id}/timeline?since=${since}`),
  artifacts: (id: string) => api.get<ArtifactOut[]>(`/api/v1/researches/${id}/artifacts`),
  review: (id: string) => api.get<ReviewOut | null>(`/api/v1/researches/${id}/review`),
};
