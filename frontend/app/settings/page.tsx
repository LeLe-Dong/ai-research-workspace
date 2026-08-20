"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, RefreshCw, Check, ArrowRight } from "lucide-react";

import { api, API_BASE } from "@/lib/api";
import { AGENT_MODE_LABELS, AGENT_MODE_KEYS } from "@/lib/labels-client";
import { LLMSettingsCard } from "@/features/settings/llm-card";
import { K8sSettingsCard } from "@/features/settings/k8s-card";

interface HealthData {
  status: string;
  service: string;
  agent_mode: string;
}

interface OpenAPIData {
  paths: Record<string, unknown>;
  info?: { title?: string; version?: string };
}

interface AgentModeInfo {
  mode: string;
  source: string;
  db_updated_at: string | null;
  env_default: string;
}

function AgentModeSwitcher({ current, disabled, onSelect }: { current: string; disabled: boolean; onSelect: (m: string) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {AGENT_MODE_KEYS.map((m) => {
        const isCurrent = m === current;
        const isPending = disabled && m !== current;
        return (
          <button
            key={m}
            type="button"
            onClick={() => onSelect(m)}
            disabled={disabled || isCurrent}
            className={
              "rounded-lg border p-3 text-left transition-all " +
              (isCurrent
                ? "border-primary bg-primary/5 ring-1 ring-primary"
                : isPending
                ? "border-muted bg-muted/30 opacity-50 cursor-not-allowed"
                : "hover:border-primary/50 hover:bg-accent/30")
            }
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-medium">{m}</span>
              {isCurrent && <Check className="h-3.5 w-3.5 text-primary" />}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{AGENT_MODE_LABELS[m]}</p>
          </button>
        );
      })}
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const [pendingMode, setPendingMode] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  // Avoid hydration mismatch: dynamic API data renders as "—" on server, real
  // values on client. Use mounted flag to render consistent placeholder.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const safe = <T,>(v: T | undefined, fallback: string = "—"): string => {
    return mounted ? (v as unknown as string) || fallback : fallback;
  };

  // Poll /admin/agent-mode more frequently when waiting for restart
  const { data: modeInfo, refetch: refetchMode } = useQuery<AgentModeInfo>({
    queryKey: ["admin", "agent-mode"],
    queryFn: () => api.get<AgentModeInfo>("/api/v1/admin/agent-mode"),
    refetchInterval: countdown !== null ? 1500 : 10_000,
  });
  const { data: health, isError: healthError, isLoading: healthLoading } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthData>("/health"),
    refetchInterval: 10_000,
  });

  const { data: openapi } = useQuery({
    queryKey: ["openapi"],
    queryFn: () => api.get<OpenAPIData>("/openapi.json"),
  });

  const setMode = useMutation({
    mutationFn: (mode: string) =>
      api.post("/api/v1/admin/agent-mode", { mode }),

    // OPTIMISTIC UPDATE: immediately flip UI to the new mode before backend restarts.
    // User sees the new mode in <100ms instead of waiting 5-10s for watcher.
    onMutate: async (mode: string) => {
      setPendingMode(mode);
      setCountdown(10);
      const prev = qc.getQueryData<AgentModeInfo>(["admin", "agent-mode"]);
      qc.setQueryData<AgentModeInfo>(["admin", "agent-mode"], (old) => ({
        mode,
        source: "db",
        db_updated_at: new Date().toISOString(),
        env_default: old?.env_default ?? "mock",
      }));
      return { prev };
    },

    onSuccess: (resp: any) => {
      toast.success(`已切换到 ${AGENT_MODE_LABELS[resp.mode as keyof typeof AGENT_MODE_LABELS] ?? resp.mode}`, {
        description: resp.message || "后端正在重启...",
      });
      qc.invalidateQueries({ queryKey: ["admin", "agent-mode"] });
      qc.invalidateQueries({ queryKey: ["health"] });
    },

    // Roll back on error (e.g. backend unreachable after watcher kills itself)
    onError: (err: Error, _mode, context: any) => {
      if (context?.prev) {
        qc.setQueryData(["admin", "agent-mode"], context.prev);
      }
      setPendingMode(null);
      setCountdown(null);
      toast.error("切换失败", { description: err.message, duration: 6000 });
    },

    onSettled: () => {
      // After 12s, force a refetch to confirm the actual backend state
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["admin", "agent-mode"] });
        qc.invalidateQueries({ queryKey: ["health"] });
        setPendingMode(null);
        setCountdown(null);
      }, 12000);
    },
  });

  // Countdown loop — when done, force-refresh
  useEffect(() => {
    if (countdown === null) return;
    if (countdown <= 0) {
      setCountdown(null);
      setPendingMode(null);
      refetchMode();
      qc.invalidateQueries({ queryKey: ["health"] });
      return;
    }
    const t = setTimeout(() => setCountdown((c) => (c ?? 0) - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown, qc, refetchMode]);

  const handleModeSelect = (mode: string) => {
    if (mode === modeInfo?.mode) return;
    setMode.mutate(mode);
  };

  const pathCount = openapi ? Object.keys(openapi.paths).length : 0;

  if (!mounted) {
    // Server render: return placeholder that matches first paint
    return (
      <div className="container mx-auto max-w-4xl space-y-6 py-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">设置</h1>
          <p className="mt-1 text-sm text-muted-foreground">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">设置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          工作区与智能体配置（只读视图，修改需重启后端服务）。
        </p>
      </div>

      {/* Service status */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">服务状态</CardTitle>
          <CardDescription>当前后端运行情况</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-muted-foreground">服务名</p>
              <p className="font-mono">{safe(health?.service, "未取得")}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">状态</p>
              <p>
                {health?.status === "ok" ? (
                  <Badge variant="success" className="h-4 px-1.5 text-[10px]">
                    运行中
                  </Badge>
                ) : healthError ? (
                  <Badge variant="destructive" className="h-4 px-1.5 text-[10px]">
                    异常
                  </Badge>
                ) : healthLoading ? (
                  <Badge variant="outline" className="h-4 px-1.5 text-[10px] text-muted-foreground">
                    加载中
                  </Badge>
                ) : (
                  <Badge variant="destructive" className="h-4 px-1.5 text-[10px]">
                    异常
                  </Badge>
                )}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">智能体模式</p>
              <p>
                <Badge variant="info" className="h-4 px-1.5 text-[10px]">
                  {mounted 
                    ? (AGENT_MODE_LABELS[(modeInfo?.mode ?? "mock") as keyof typeof AGENT_MODE_LABELS] ?? modeInfo?.mode ?? "—")
                    : "—"}
                </Badge>
                <span className="ml-2 font-mono text-[10px] text-muted-foreground">
                  {safe(modeInfo?.mode)}
                  {mounted && modeInfo?.source === "db" && <span className="ml-1 text-[9px] text-amber-600">（DB 覆盖）</span>}
                </span>
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">API 端点数</p>
              <p className="font-mono">{mounted ? pathCount : 0}</p>
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground">
            后端地址：<code className="rounded bg-muted px-1">{API_BASE}</code>（来自 NEXT_PUBLIC_API_BASE 环境变量）
          </p>
        </CardContent>
      </Card>

      {/* Agent modes */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">可用的智能体模式</CardTitle>
          <CardDescription>
            通过 <code className="rounded bg-muted px-1">AIRW_AGENT_MODE</code> 环境变量切换（需重启后端）
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <AgentModeSwitcher
            current={modeInfo?.mode ?? "mock"}
            disabled={setMode.isPending || pendingMode !== null}
            onSelect={handleModeSelect}
          />
          {pendingMode && countdown !== null && (
            <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>正在切换到 {AGENT_MODE_LABELS[pendingMode as keyof typeof AGENT_MODE_LABELS] ?? pendingMode}，后端重启中...</span>
              <span className="ml-auto font-mono">{countdown}s</span>
            </div>
          )}
          <div className="space-y-2 border-t pt-3 text-xs text-muted-foreground">
            {AGENT_MODE_KEYS.map((m) => (
              <p key={m}>
                <span className="font-mono font-medium text-foreground">{m}</span>
                {m === "mock" && "：固定剧本（4 秒），无需 API key。Demo 模式。"}
                {m === "llm" && "：调用下方「LLM 模型」卡片配置的 provider（stepfun / kimi / minimax / openai_compat）。所有 OpenAI 兼容协议。"}
                {m === "hermes-researcher" && "：Shell out 到 hermes chat --cli。复用 hermes 自带 skill 体系（arxiv / feeds）。"}
              </p>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* LLM model config */}
      <div className="grid gap-6 md:grid-cols-2">
        <LLMSettingsCard />
        <K8sSettingsCard />
      </div>

      {/* Available modes reference */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">快捷键</CardTitle>
          <CardDescription>提高日常操作效率</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex items-center justify-between border-b py-1.5">
            <span>打开命令面板</span>
            <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>
          </div>
          <div className="flex items-center justify-between border-b py-1.5">
            <span>切换主题</span>
            <span className="text-xs text-muted-foreground">顶栏按钮</span>
          </div>
          <div className="flex items-center justify-between py-1.5">
            <span>新建研究</span>
            <span className="text-xs text-muted-foreground">顶栏 / 命令面板</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
