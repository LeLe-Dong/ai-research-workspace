"use client";
import { useQuery } from "@tanstack/react-query";
import { reportApi } from "./api-report";
import { summaryApi } from "./api-summary";

export function useReport(id: string) {
  return useQuery({
    queryKey: ["research", id, "report"],
    queryFn: () => reportApi.get(id),
    enabled: !!id,
  });
}

export function useCompletedResearches() {
  return useQuery({
    queryKey: ["completed-researches"],
    queryFn: reportApi.listCompleted,
    staleTime: 30_000,
  });
}

export function useResearchSummary(id: string) {
  return useQuery({
    queryKey: ["research", id, "summary"],
    queryFn: () => summaryApi.get(id),
    enabled: !!id,
    staleTime: 10_000,
    refetchInterval: (q) => {
      // Poll only when actively running; 5s is enough for progress updates.
      const status = q.state.data?.status;
      return status === "running" || status === "pending" ? 5_000 : false;
    },
  });
}
