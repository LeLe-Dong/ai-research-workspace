"use client";
import { useQuery } from "@tanstack/react-query";
import { reportApi } from "./api-report";

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
