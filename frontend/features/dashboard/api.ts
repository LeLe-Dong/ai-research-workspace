import { api } from "@/lib/api";
import type { DashboardData } from "@/lib/types";

export const dashboardApi = {
  getAll: () => api.get<DashboardData>("/api/v1/dashboard"),
};
