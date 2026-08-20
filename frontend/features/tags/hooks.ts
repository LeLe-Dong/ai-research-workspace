import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import type { Tag } from "@/lib/types";

export function useTags() {
  return useQuery({
    queryKey: ["tags"],
    queryFn: async () => {
      const data = await api.get<{ tags: Tag[] }>("/api/v1/tags");
      return data.tags;
    },
  });
}

export function useCreateTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, color }: { name: string; color?: string }) => {
      return api.post<Tag>("/api/v1/tags", { name, color: color || "blue" });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tags"] });
      toast.success("标签已创建");
    },
  });
}

export function useAttachTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ researchId, name, tagId }: { researchId: string; name?: string; tagId?: string }) => {
      const payload: any = {};
      if (name) payload.name = name;
      if (tagId) payload.tag_id = tagId;
      return api.post<any>(`/api/v1/tags/researches/${researchId}/attach`, payload);
    },
    onSuccess: (data, variables) => {
      // Only invalidate the specific research + tags, not everything
      qc.invalidateQueries({ queryKey: ["research", variables.researchId] });
      qc.invalidateQueries({ queryKey: ["tags"] });
      toast.success(`已添加标签：${data.tag.name}`);
    },
  });
}

export function useDetachTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ researchId, tagId }: { researchId: string; tagId: string }) => {
      return api.post<any>(`/api/v1/tags/researches/${researchId}/detach?tag_id=${tagId}`);
    },
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ["research", variables.researchId] });
      qc.invalidateQueries({ queryKey: ["tags"] });
      toast.success("已移除标签");
    },
  });
}
