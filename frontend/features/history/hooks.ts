import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import type { HistoryVersion, HistoryDiff, ForkResponse } from "@/lib/types";

export function useHistoryList() {
  return useQuery({
    queryKey: ["history", "list"],
    queryFn: async () => {
      const items = await api.get<any[]>("/api/v1/researches?limit=50");
      return items;
    },
  });
}

export function useVersions(researchId: string | undefined) {
  return useQuery({
    queryKey: ["history", "versions", researchId],
    queryFn: async () => {
      const data = await api.get<{ versions: HistoryVersion[] }>(`/api/v1/history/${researchId}/versions`);
      return data.versions;
    },
    enabled: !!researchId,
  });
}

export function useVersionDetail(researchId: string | undefined, version: number | null) {
  return useQuery({
    queryKey: ["history", "version", researchId, version],
    queryFn: async () => {
      return api.get(`/api/v1/history/${researchId}/versions/${version}`);
    },
    enabled: !!researchId && version != null,
  });
}

export function useDiff(researchId: string | undefined, v1: number | null, v2: number | null) {
  return useQuery({
    queryKey: ["history", "diff", researchId, v1, v2],
    queryFn: async () => {
      const url = `/api/v1/history/${researchId}/diff?v1=${v1}&v2=${v2}`;
      const data = await api.get<HistoryDiff>(url);
      return data;
    },
    enabled: !!researchId && v1 != null && v2 != null && v1 !== v2,
  });
}

export function useFork() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ researchId, version, commitMessage }: { researchId: string; version: number; commitMessage?: string }) => {
      const qs = new URLSearchParams({ version: String(version) });
      if (commitMessage) qs.set("commit_message", commitMessage);
      const data = await api.post<ForkResponse>(`/api/v1/history/${researchId}/fork?${qs.toString()}`);
      return data;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["history"] });
      qc.invalidateQueries({ queryKey: ["researches"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(`已 fork：${data.title}`);
    },
  });
}

export function useRollback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ researchId, version, commitMessage }: { researchId: string; version: number; commitMessage?: string }) => {
      const qs = new URLSearchParams({ version: String(version) });
      if (commitMessage) qs.set("commit_message", commitMessage);
      const data = await api.post<ForkResponse>(`/api/v1/history/${researchId}/rollback?${qs.toString()}`);
      return data;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["history"] });
      qc.invalidateQueries({ queryKey: ["researches"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(`已回滚：${data.title}`);
    },
  });
}
