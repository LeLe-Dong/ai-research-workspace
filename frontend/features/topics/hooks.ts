import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";

export interface TopicSession {
  id: string;
  iteration: number;
  title: string;
  goal: string;
  constraints: string;
  expected_output: string;
  depth: string;
  priority: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TopicItem {
  id: string;
  name: string;
  description: string;
  iteration_count: number;
  completed_count: number;
  latest_status: string | null;
  latest_score: number | null;
  latest_title: string | null;
  created_at: string;
  updated_at: string;
}

export interface TopicDetail extends TopicItem {
  sessions: TopicSession[];
  total: number;
}

export interface GeneratedPlan {
  title: string;
  goal: string;
  constraints: string;
  expected_output: string;
  depth: "quick" | "standard" | "deep";
  priority: "low" | "medium" | "high";
  requires_k8s_validation: number;
}

export function useTopics() {
  return useQuery({
    queryKey: ["topics"],
    queryFn: async () => {
      const data = await api.get<{ items: TopicItem[]; total: number }>("/api/v1/topics");
      return data.items;
    },
  });
}

export function useTopic(topicId: string | undefined) {
  return useQuery({
    queryKey: ["topics", topicId],
    queryFn: async () => api.get<TopicDetail>(`/api/v1/topics/${topicId}`),
    enabled: !!topicId,
  });
}

export function useCreateTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, description }: { name: string; description: string }) => {
      return api.post<{ id: string; name: string }>("/api/v1/topics", { name, description });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["topics"] });
      toast.success("主题已创建");
    },
    onError: (e) => toast.error("创建主题失败", { description: (e as Error).message }),
  });
}

export function useIterateTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      topicId,
      goal,
      constraints,
      expected_output,
      depth,
      priority,
      commit_message,
    }: {
      topicId: string;
      goal?: string;
      constraints?: string;
      expected_output?: string;
      depth?: string;
      priority?: string;
      commit_message?: string;
    }) => {
      return api.post<TopicSession>(`/api/v1/topics/${topicId}/iterate`, {
        goal,
        constraints,
        expected_output,
        depth,
        priority,
        commit_message,
      });
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["topics"] });
      toast.success(`已启动迭代 ${data.iteration}`, { description: data.title });
    },
    onError: (e) => toast.error("发起迭代失败", { description: (e as Error).message }),
  });
}

export function useGeneratePlan() {
  return useMutation({
    mutationFn: async ({ subject, useLlm }: { subject: string; useLlm?: boolean }) => {
      const data = await api.post<{ subject: string; plan: GeneratedPlan; source: string }>(
        "/api/v1/researches/generate-plan",
        { subject, use_llm: useLlm ?? true }
      );
      return data;
    },
    onError: (e) => toast.error("生成研究方案失败", { description: (e as Error).message }),
  });
}
