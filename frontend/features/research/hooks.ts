"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { researchApi } from "./api";
import type { ResearchCreate, ResearchDetail } from "@/lib/types";

function resolveApiBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return "";
}

export function useResearchList(tag?: string, q?: string) {
  return useQuery({
    queryKey: ["researches", tag ?? "all", q ?? ""],
    queryFn: () => researchApi.list({ tag, q }),
  });
}

export function useResearch(id: string) {
  return useQuery({
    queryKey: ["research", id],
    queryFn: () => researchApi.get(id) as Promise<ResearchDetail>,
    enabled: !!id,
  });
}

export function useCreateResearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ResearchCreate) => researchApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["researches"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useDeleteResearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => researchApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["researches"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useStartResearch(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const apiBase = resolveApiBase();
      const r = await fetch(`${apiBase}/api/v1/researches/${id}/start`, {
        method: "POST",
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status}: ${body.slice(0, 200)}`);
      }
      return r.json();
    },
    // No onSuccess invalidation — the execute page fetches its own data,
    // and SSE pushes live updates. Invalidate here would cause a burst of
    // redundant refetches that compete with the page transition.
  });
}
