"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { researchApi } from "./api";
import type { ResearchCreate, ResearchDetail } from "@/lib/types";

export function useResearchList(tag?: string) {
  return useQuery({
    queryKey: ["researches", tag ?? "all"],
    queryFn: () => researchApi.list({ tag }),
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
      const apiBase = (typeof window !== "undefined"
        ? `${window.location.protocol}//${window.location.hostname}:8003`
        : "http://127.0.0.1:8003");
      const r = await fetch(`${apiBase}/api/v1/researches/${id}/start`, {
        method: "POST",
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status}: ${body.slice(0, 200)}`);
      }
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["research", id] });
      qc.invalidateQueries({ queryKey: ["researches"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
