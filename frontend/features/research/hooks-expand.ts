import { useState, useCallback } from "react";

interface ExpandResult {
  original: string;
  expanded: string;
  model: string;
  cached: boolean;
  tokens_used: number | null;
}

export function useExpandGoal() {
  const [isExpanding, setIsExpanding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const expand = useCallback(async (goal: string): Promise<ExpandResult | null> => {
    if (!goal.trim()) {
      setError("目标不能为空");
      return null;
    }
    setIsExpanding(true);
    setError(null);
    try {
      const r = await fetch("/api/v1/expand/goal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
        throw new Error(data.detail || `HTTP ${r.status}`);
      }
      const result = (await r.json()) as ExpandResult;
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "扩写失败";
      setError(msg);
      return null;
    } finally {
      setIsExpanding(false);
    }
  }, []);

  return { expand, isExpanding, error };
}
