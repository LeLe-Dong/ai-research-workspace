"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { executeApi } from "./api-execute";

export function useTasks(id: string) {
  return useQuery({
    queryKey: ["research", id, "tasks"],
    queryFn: () => executeApi.tasks(id),
    enabled: !!id,
    // SSE pushes real-time updates. No refetchInterval needed —
    // the SSE hook handles polling fallback when SSE is unavailable.
  });
}

export function useTimeline(id: string) {
  return useQuery({
    queryKey: ["research", id, "timeline"],
    queryFn: () => executeApi.timeline(id),
    enabled: !!id,
    // SSE pushes real-time updates. No refetchInterval needed.
  });
}

export function useArtifacts(id: string) {
  return useQuery({
    queryKey: ["research", id, "artifacts"],
    queryFn: () => executeApi.artifacts(id),
    enabled: !!id,
    // SSE pushes real-time updates. No refetchInterval needed.
  });
}

export function useReview(id: string) {
  return useQuery({
    queryKey: ["research", id, "review"],
    queryFn: () => executeApi.review(id),
    enabled: !!id,
    // SSE pushes real-time updates. No refetchInterval needed.
  });
}

export function useStartResearch(id: string) {
  const qc = useQueryClient();
  return async () => {
    // Fire-and-forget: the execute page listens via SSE for live updates.
    // Don't block the UI or trigger redundant refetches.
    executeApi.start(id).catch(() => {
      // Silently fail — the SSE stream will surface errors to the user.
    });
  };
}
