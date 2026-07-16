"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { executeApi } from "./api-execute";

export function useTasks(id: string) {
  return useQuery({
    queryKey: ["research", id, "tasks"],
    queryFn: () => executeApi.tasks(id),
    enabled: !!id,
    refetchInterval: 8_000,  // SSE pushes; polling is fallback
  });
}

export function useTimeline(id: string) {
  return useQuery({
    queryKey: ["research", id, "timeline"],
    queryFn: () => executeApi.timeline(id),
    enabled: !!id,
    refetchInterval: 8_000,  // SSE pushes; polling is fallback
  });
}

export function useArtifacts(id: string) {
  return useQuery({
    queryKey: ["research", id, "artifacts"],
    queryFn: () => executeApi.artifacts(id),
    enabled: !!id,
    refetchInterval: 8_000,  // SSE pushes; polling is fallback
  });
}

export function useReview(id: string) {
  return useQuery({
    queryKey: ["research", id, "review"],
    queryFn: () => executeApi.review(id),
    enabled: !!id,
    refetchInterval: 8_000,  // SSE pushes; polling is fallback
  });
}

export function useStartResearch(id: string) {
  const qc = useQueryClient();
  return async () => {
    await executeApi.start(id);
    qc.invalidateQueries({ queryKey: ["research", id] });
  };
}
