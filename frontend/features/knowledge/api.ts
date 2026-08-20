/** Knowledge base API client. */
import { api } from "@/lib/api";

export interface KnowledgeDoc {
  id: string;
  filename: string;
  byte_size: number;
  uploaded_at: string;
  sections_count: number;
}

export interface KnowledgeStyle {
  id: string;
  name: string;
  dimensions: string[];
  tone: string;
  length_pref: string;
  quantification: string;
  custom_instructions: string;
  source_doc_ids: string[];
  is_active: boolean;
  updated_at: string;
}

export const knowledgeApi = {
  upload: async (file: File): Promise<KnowledgeDoc> => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${(typeof window !== "undefined" ? window.location.origin : "")}/api/v1/knowledge/uploads`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },

  listDocuments: async (): Promise<{ items: KnowledgeDoc[]; total: number }> =>
    api.get("/api/v1/knowledge/documents"),

  deleteDocument: async (id: string): Promise<void> => {
    await api.delete(`/api/v1/knowledge/documents/${id}`);
  },

  extractStyle: async (name = "auto"): Promise<KnowledgeStyle> => {
    const r = await fetch(
      `${(typeof window !== "undefined" ? window.location.origin : "")}/api/v1/knowledge/styles/extract?name=${encodeURIComponent(name)}`,
      { method: "POST" }
    );
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },

  listStyles: async (): Promise<{ items: KnowledgeStyle[]; total: number }> =>
    api.get("/api/v1/knowledge/styles"),

  currentStyle: async (): Promise<{ active: KnowledgeStyle | null }> =>
    api.get("/api/v1/knowledge/styles/current"),

  activateStyle: async (id: string): Promise<KnowledgeStyle> => {
    const r = await fetch(
      `${(typeof window !== "undefined" ? window.location.origin : "")}/api/v1/knowledge/styles/${id}/activate`,
      { method: "POST" }
    );
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },

  matchStyles: async (
    goal: string,
    constraints = "",
    useLlmRerank = false
  ): Promise<{
    matches: Array<{
      style: KnowledgeStyle;
      score: number;
      matched_keywords: string[];
      sample_dimensions: string[];
      llm_score?: number;
      llm_reason?: string;
    }>;
    total_styles: number;
    used_llm_rerank?: boolean;
  }> => {
    const r = await fetch(
      `${(typeof window !== "undefined" ? window.location.origin : "")}/api/v1/knowledge/styles/match`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal, constraints, use_llm_rerank: useLlmRerank }),
      }
    );
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },
};