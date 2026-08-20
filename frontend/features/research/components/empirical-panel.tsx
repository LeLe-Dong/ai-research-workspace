"use client";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Cpu, MemoryStick, Hash, ExternalLink, Activity, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

interface EmpiricalData {
  workload: string;
  workload_description: string;
  image: string;
  namespace: string;
  cluster: string;
  pod_name: string;
  pod_status: string;
  node: string | null;
  pod_ip: string | null;
  conditions: string[];
  elapsed_sec: number;
  benchmark_metrics: Record<string, string>;
  resource_usage: Record<string, string>;
  log_excerpt: string;
}

function StatusBadge({ status }: { status: string }) {
  const lower = status.toLowerCase();
  if (lower === "running" || lower === "succeeded") {
    return <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/15"><CheckCircle2 className="mr-1 h-3 w-3" />{status}</Badge>;
  }
  if (lower === "pending") {
    return <Badge className="bg-amber-500/15 text-amber-700 dark:text-amber-300 hover:bg-amber-500/15"><AlertTriangle className="mr-1 h-3 w-3" />{status}</Badge>;
  }
  if (lower === "failed") {
    return <Badge className="bg-red-500/15 text-red-700 dark:text-red-300 hover:bg-red-500/15"><XCircle className="mr-1 h-3 w-3" />{status}</Badge>;
  }
  return <Badge variant="outline"><Activity className="mr-1 h-3 w-3" />{status}</Badge>;
}

export function EmpiricalPanel({ researchId }: { researchId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["research", researchId, "k8s-validation"],
    queryFn: async () => {
      // Use the generic api.get to fetch the artifact list and pick the
      // k8s-validation one. Falls back to null on any error.
      try {
        const arts = await api.get<Array<{ kind: string; title: string; content: string; created_at: string }>>(
          `/api/v1/researches/${researchId}/artifacts`
        );
        const kv = arts.find((a) => a.kind === "k8s-validation");
        if (!kv) return null;
        return JSON.parse(kv.content) as EmpiricalData;
      } catch {
        return null;
      }
    },
    refetchInterval: 5_000,  // poll while validation is running
  });

  if (isLoading) {
    return (
      <div className="space-y-3 p-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-3 py-6 text-center text-muted-foreground">
        <FlaskConical className="h-8 w-8 opacity-40" />
        <p className="text-xs">暂无实证数据</p>
        <p className="text-[10px]">研究跑完后且勾选 K8s 验证时会显示</p>
      </div>
    );
  }

  const metricKeys = Object.keys(data.benchmark_metrics || {});
  const resourceKeys = Object.keys(data.resource_usage || {});

  return (
    <div className="space-y-3 p-3 text-xs">
      {/* Header card */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-1.5 text-sm">
            <FlaskConical className="h-4 w-4 text-blue-500" />
            K8s 集群实证数据
            <StatusBadge status={data.pod_status} />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 text-[11px]">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">工作负载:</span>
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
              {data.workload}
            </code>
            <span className="text-muted-foreground">·</span>
            <span className="truncate text-muted-foreground" title={data.image}>
              {data.image}
            </span>
          </div>
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            {data.workload_description}
          </p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 pt-1 text-[11px]">
            <div><span className="text-muted-foreground">集群</span> · {data.cluster || "-"}</div>
            <div><span className="text-muted-foreground">命名空间</span> · {data.namespace}</div>
            <div><span className="text-muted-foreground">节点</span> · {data.node || "(未调度)"}</div>
            <div><span className="text-muted-foreground">Pod IP</span> · {data.pod_ip || "-"}</div>
            <div className="col-span-2">
              <span className="text-muted-foreground">Pod</span> ·{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">
                {data.pod_name}
              </code>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Benchmark metrics */}
      {metricKeys.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-1.5 text-sm">
              <Activity className="h-4 w-4 text-emerald-500" />
              Benchmark 指标
              <span className="ml-auto text-[10px] font-normal text-muted-foreground">
                耗时 {data.elapsed_sec}s
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2">
              {metricKeys.map((k) => (
                <div key={k} className="rounded-md border bg-muted/30 px-2 py-1.5">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {k.replace(/_/g, " ")}
                  </p>
                  <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums">
                    {data.benchmark_metrics[k]}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Resource usage */}
      {resourceKeys.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-1.5 text-sm">
              <Cpu className="h-4 w-4 text-amber-500" />
              资源使用
              {data.resource_usage.source && (
                <span className="ml-auto text-[10px] font-normal text-muted-foreground">
                  {data.resource_usage.source}
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1 text-[11px]">
              {Object.entries(data.resource_usage)
                .filter(([k]) => k !== "source" && k !== "_note")
                .map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between">
                    <span className="text-muted-foreground">{k.replace(/_/g, " ")}</span>
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                      {v}
                    </code>
                  </div>
                ))}
              {data.resource_usage._note && (
                <p className="mt-1 text-[10px] italic text-muted-foreground">
                  {data.resource_usage._note}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Log excerpt */}
      {data.log_excerpt && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-1.5 text-sm">
              <Hash className="h-4 w-4 text-zinc-500" />
              Pod 日志片段
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-48 overflow-auto rounded-md border bg-zinc-950 p-2 font-mono text-[10px] leading-relaxed text-zinc-300">
              {data.log_excerpt}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
