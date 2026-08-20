"use client";
import { useState, useMemo, lazy, Suspense } from "react";
import { Download, FileText, GitBranch, BarChart3, CheckCircle2, Loader2, Server, Target, ListChecks } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

import type { ArtifactOut, ReviewOut } from "@/lib/types";

// Dynamic imports for heavy libraries (mermaid ~200KB, react-markdown ~100KB)
const MermaidRender = lazy(() =>
  import("./mermaid-render").then(m => ({ default: m.MermaidRender }))
);
const MarkdownRender = lazy(() =>
  import("./markdown-render").then(m => ({ default: m.MarkdownRender }))
);

const ICON_FOR: Record<string, typeof FileText> = {
  mermaid: GitBranch,
  markdown: FileText,
  table: BarChart3,
  review: CheckCircle2,
  "k8s-experiment": Server,
  "k8s-validation": Server,
};

function downloadArtifact(a: ArtifactOut) {
  const blob = new Blob([a.content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a2 = document.createElement("a");
  a2.href = url;
  const ext = a.kind === "mermaid" ? "mmd" : "md";
  a2.download = `${a.title.replace(/\s+/g, "-").toLowerCase()}.${ext}`;
  document.body.appendChild(a2);
  a2.click();
  document.body.removeChild(a2);
  URL.revokeObjectURL(url);
}

function RenderArtifact({ a }: { a: ArtifactOut }) {
  if (a.kind === "mermaid") {
    return (
      <Suspense fallback={<div className="p-4 text-center text-xs text-muted-foreground"><Loader2 className="inline h-3 w-3 animate-spin" /> 加载图表…</div>}>
        <MermaidRender code={a.content} />
      </Suspense>
    );
  }
  if (a.kind === "markdown" || a.kind === "table") {
    return (
      <Suspense fallback={<div className="p-4 text-center text-xs text-muted-foreground"><Loader2 className="inline h-3 w-3 animate-spin" /> 加载渲染…</div>}>
        <MarkdownRender content={a.content} />
      </Suspense>
    );
  }
  return <pre className="p-3 text-xs">{a.content}</pre>;
}

export function K8sExperimentPanel({ artifact }: { artifact: ArtifactOut }) {
  let data: any = null;
  try { data = JSON.parse(artifact.content); } catch { /* ignore */ }
  if (!data || typeof data !== "object") {
    return <pre className="p-3 text-xs">{artifact.content}</pre>;
  }

  const checks: any[] = data.checks ?? [];
  const workloads: any[] = data.workloads ?? [];
  const passed = data.passed ?? 0;
  const total = data.total ?? checks.length;
  const skipped = data.skipped ?? 0;
  const actualTotal = data.actual_total ?? (total - skipped);

  const typeLabel: Record<string, string> = {
    pod_ready: "Pod 就绪",
    service_ready: "Service 端点",
    pod_log_match: "日志匹配",
    http_ok: "HTTP 可达",
  };

  const statusText = (c: any): string => {
    if (c.skipped) return "已跳过";
    return c.passed ? "通过" : "失败";
  };

  const statusClass = (c: any): string => {
    if (c.skipped) return "text-zinc-500 bg-zinc-500/10 border-zinc-500/30";
    return c.passed
      ? "text-emerald-600 bg-emerald-500/10 border-emerald-500/30 dark:text-emerald-300"
      : "text-red-600 bg-red-500/10 border-red-500/30 dark:text-red-300";
  };

  return (
    <div className="space-y-4 p-4">
      {/* Purpose: what this experiment verifies (goal ↔ test alignment) */}
      <Card>
        <CardContent className="space-y-2 p-3">
          <div className="flex items-center gap-2">
            <Target className="h-3.5 w-3.5 text-cyan-500" />
            <p className="text-xs font-semibold">实测目的</p>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {data.purpose || "围绕研究目标部署真实工作负载并验证关键能力。"}
          </p>
          {data.goal && (
            <p className="text-[10px] text-muted-foreground/70">
              研究目标：{String(data.goal).slice(0, 200)}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Overview */}
      <Card>
        <CardContent className="space-y-2 p-3">
          <div className="flex items-center gap-2">
            <Server className="h-3.5 w-3.5 text-blue-500" />
            <p className="text-xs font-semibold">试验概览</p>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded border bg-muted/40 p-2">
              <p className="text-[10px] text-muted-foreground">试验</p>
              <p className="truncate font-medium">{data.experiment_name || "—"}</p>
            </div>
            <div className="rounded border bg-muted/40 p-2">
              <p className="text-[10px] text-muted-foreground">集群</p>
              <p className="font-medium">{data.cluster || "—"}</p>
            </div>
            <div className="rounded border bg-muted/40 p-2">
              <p className="text-[10px] text-muted-foreground">命名空间</p>
              <p className="truncate font-mono text-[10px]">{data.namespace || "—"}</p>
            </div>
            <div className="rounded border p-2" style={{ borderColor: actualTotal > 0 && passed === actualTotal ? "rgb(16 185 129 / 0.4)" : actualTotal === 0 ? undefined : "rgb(245 158 11 / 0.4)" }}>
              <p className="text-[10px] text-muted-foreground">断言通过率</p>
              <p className="font-bold">
                {passed}/{actualTotal}
                <span className="ml-1 text-[10px] font-normal text-muted-foreground">
                  {actualTotal > 0 ? (passed === actualTotal ? "全部通过" : "有失败") : "无断言"}
                </span>
                {skipped > 0 && <span className="ml-1 text-[10px] font-normal text-zinc-500">（{skipped} 项已跳过）</span>}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Workloads */}
      {workloads.length > 0 && (
        <Card>
          <CardContent className="space-y-2 p-3">
            <div className="flex items-center gap-2">
              <ListChecks className="h-3.5 w-3.5 text-indigo-500" />
              <p className="text-xs font-semibold">部署的工作负载（{workloads.length}）</p>
            </div>
            <div className="space-y-1">
              {workloads.map((w, i) => (
                <div key={i} className="rounded border px-2 py-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="min-w-0 truncate">
                      <span className="text-muted-foreground">{w.kind}</span>{" "}
                      <span className="font-medium">{w.name}</span>
                    </span>
                    <span className="ml-2 shrink-0 truncate text-[10px] text-muted-foreground">
                      {w.image || (w.kind === "Service" ? "(Service)" : "")}
                    </span>
                  </div>
                  {w.command && (
                    <p className="mt-1 whitespace-pre-wrap break-words rounded bg-black/5 p-1.5 font-mono text-[9px] leading-relaxed text-muted-foreground dark:bg-white/5">
                      {w.command.slice(0, 300)}
                      {w.command.length > 300 ? "…" : ""}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Checks */}
      {checks.length > 0 && (
        <Card>
          <CardContent className="space-y-2 p-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
              <p className="text-xs font-semibold">验证断言结果（{checks.length}）</p>
            </div>
            <div className="space-y-1.5">
              {checks.map((c, i) => (
                <div
                  key={i}
                  className="rounded border px-2.5 py-2 text-xs"
                  style={{ borderColor: c.skipped ? "rgb(113 113 122 / 0.3)" : c.passed ? "rgb(16 185 129 / 0.3)" : "rgb(239 68 68 / 0.3)", background: c.skipped ? "rgb(113 113 122 / 0.05)" : c.passed ? "rgb(16 185 129 / 0.05)" : "rgb(239 68 68 / 0.05)" }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span>{c.skipped ? "⏭️" : c.passed ? "✅" : "❌"}</span>
                      <span className="truncate font-medium">{c.name}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1">
                      <Badge variant="outline" className={"h-4 px-1.5 text-[9px] " + statusClass(c)}>
                        {statusText(c)}
                      </Badge>
                      <Badge variant="outline" className="h-4 shrink-0 text-[9px]">
                        {typeLabel[c.type] || c.type}
                      </Badge>
                    </span>
                  </div>
                  <p className="mt-1.5 text-[10px] leading-relaxed text-muted-foreground">
                    <span className="font-medium text-foreground/80">目标：</span>{c.target}
                    <span className="mx-1 text-muted-foreground/40">·</span>
                    <span className="font-medium text-foreground/80">期望：</span>{c.expect}
                    {c.skipped && <span className="ml-1 text-zinc-500">（计划中未部署该资源，跳过）</span>}
                  </p>
                  {c.explain && (
                    <p className="mt-1.5 rounded bg-black/5 p-1.5 text-[10px] leading-relaxed text-muted-foreground dark:bg-white/5">
                      <span className="font-medium text-foreground/80">验证点：</span>{c.explain}
                    </p>
                  )}
                  {!c.passed && c.fail_reason && (
                    <p className="mt-1 rounded bg-red-500/5 p-1.5 text-[10px] leading-relaxed text-red-600/90 dark:text-red-300/90">
                      <span className="font-medium">未通过原因：</span>{c.fail_reason}
                    </p>
                  )}
                  {c.evidence && !c.explain && (
                    <p className="mt-0.5 whitespace-pre-wrap break-words text-[10px] text-muted-foreground/70">
                      {c.evidence}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function ReviewPanel({ review }: { review?: ReviewOut | null }) {
  if (!review) return null;
  const dims = review.dimensions || {};
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-baseline justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          智能评审 Score
        </p>
        <Badge variant={review.overall_score >= review.threshold ? "success" : "warning"} className="h-5 px-2 text-xs">
          {review.overall_score.toFixed(1)} / 10
        </Badge>
      </div>
      <div className="space-y-1.5">
        {Object.entries(dims).map(([k, v]) => {
          const score = v as number;
          return (
            <div key={k} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</span>
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                  <div
                    className={
                      "h-full " +
                      (score >= 8 ? "bg-emerald-500" : score >= 6 ? "bg-amber-500" : "bg-destructive")
                    }
                    style={{ width: `${score * 10}%` }}
                  />
                </div>
                <span className="w-8 text-right font-mono text-[10px]">{score.toFixed(1)}</span>
              </div>
            </div>
          );
        })}
      </div>
      {review.strengths && (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-2.5 text-xs">
          <p className="font-medium text-emerald-700 dark:text-emerald-300">优势</p>
          <p className="mt-1 text-muted-foreground">{review.strengths}</p>
        </div>
      )}
      {review.weaknesses && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs">
          <p className="font-medium text-amber-700 dark:text-amber-300">不足</p>
          <p className="mt-1 text-muted-foreground">{review.weaknesses}</p>
        </div>
      )}
      {review.suggestions && (
        <div className="rounded-md border bg-muted/50 p-2.5 text-xs">
          <p className="font-medium">建议</p>
          <p className="mt-1 text-muted-foreground">{review.suggestions}</p>
        </div>
      )}
    </div>
  );
}

export function LiveArtifact({ artifacts, review }: { artifacts?: ArtifactOut[]; review?: ReviewOut | null }) {
  const items = artifacts ?? [];
  // Prefer showing the k8s experiment first (real measured results), then
  // the report; fall back to the first artifact.
  const k8sItem = items.find((a) => a.kind === "k8s-experiment" || a.kind === "k8s-validation");
  const reportItem = items.find((a) => a.kind === "markdown");
  const defaultTab = k8sItem?.id ?? reportItem?.id ?? items[0]?.id ?? "review";

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          产物面板
        </p>
        <p className="mt-0.5 text-[10px] text-muted-foreground">
          {items.length} 个产物已就绪
        </p>
      </div>

      <Tabs defaultValue={defaultTab} className="flex-1 flex flex-col">
        <div className="border-b px-2">
          <TabsList className="h-9 bg-transparent p-0">
            {items.map((a) => {
              const Icon = ICON_FOR[a.kind] || FileText;
              return (
                <TabsTrigger
                  key={a.id}
                  value={a.id}
                  className="h-9 gap-1.5 rounded-none border-b-2 border-transparent px-3 text-xs data-[state=active]:border-primary data-[state=active]:bg-transparent"
                >
                  <Icon className="h-3 w-3" />
                  {a.title.length > 18 ? a.title.slice(0, 18) + "..." : a.title}
                </TabsTrigger>
              );
            })}
            {review && (
              <TabsTrigger
                value="review"
                className="h-9 gap-1.5 rounded-none border-b-2 border-transparent px-3 text-xs data-[state=active]:border-primary data-[state=active]:bg-transparent"
              >
                <CheckCircle2 className="h-3 w-3" />
                智能评审
              </TabsTrigger>
            )}
          </TabsList>
        </div>

        <ScrollArea className="flex-1">
          {items.map((a) => (
            <TabsContent key={a.id} value={a.id} className="m-0">
              <div className="flex items-center justify-end border-b px-2 py-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => downloadArtifact(a)}
                >
                  <Download className="h-3 w-3" />
                  .{a.kind === "mermaid" ? "mmd" : "md"}
                </Button>
              </div>
              {a.kind === "k8s-experiment" ? (
                <K8sExperimentPanel artifact={a} />
              ) : (
                <RenderArtifact a={a} />
              )}
            </TabsContent>
          ))}
          {review && (
            <TabsContent value="review" className="m-0">
              <ReviewPanel review={review} />
            </TabsContent>
          )}
        </ScrollArea>
      </Tabs>
    </div>
  );
}
