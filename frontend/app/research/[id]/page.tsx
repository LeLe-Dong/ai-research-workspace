"use client";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { FlaskConical, ArrowLeft, Loader2, Clock, History, Activity, Sparkles, FileText, AlertTriangle, RotateCcw } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";
import { useResearch } from "@/features/research/hooks";
import { TagSelector } from "@/features/tags/components/tag-selector";
import { useDetachTag } from "@/features/tags/hooks";
import { useStartResearch } from "@/features/research/hooks";

const statusVariant = {
  pending: "secondary",
  running: "info",
  completed: "success",
  failed: "destructive",
} as const;

const statusLabel: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
};

export default function ResearchDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { data, isLoading, error } = useResearch(params.id);
  const detachTag = useDetachTag();
  const start = useStartResearch(params.id);
  const [starting, setStarting] = useState(false);
  const onStart = async () => {
    if (starting) return;
    setStarting(true);
    try {
      await start.mutateAsync();
      toast.success("已重新执行", { description: "正在跳转到执行视图…" });
      // Navigate to execute view so user can see live progress
      router.push(`/research/${params.id}/execute`);
    } catch (e) {
      toast.error("启动失败", { description: (e as Error).message });
      setStarting(false);
    }
    // Note: not resetting starting on success - we're navigating away
  };

  if (error) {
    return (
      <div className="container max-w-none px-6 py-6">
        <Button variant="ghost" asChild className="mb-4 -ml-2">
          <Link href="/research"><ArrowLeft className="h-3.5 w-3.5" /> Back</Link>
        </Button>
        <Card>
          <CardContent className="py-8 text-center text-sm text-destructive">
            加载研究失败： {(error as Error).message}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container max-w-none px-6 py-6">
      <Button variant="ghost" asChild className="mb-4 -ml-2">
        <Link href="/research"><ArrowLeft className="h-3.5 w-3.5" /> 返回研究列表</Link>
      </Button>

      {isLoading || !data ? (
        <div className="space-y-3">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="mt-6 h-32 w-full" />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          {/* Main content */}
          <div>
            <div className="mb-6 flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                <FlaskConical className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="flex-1">
                <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant={statusVariant[data.status]} className="h-4 px-1.5 text-[10px]">
                    {statusLabel[data.status] || data.status}
                  </Badge>
                  <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
                    深度: {data.depth}
                  </Badge>
                  <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
                    优先级: {data.priority}
                  </Badge>
                  <span>创建于 {formatRelativeTime(data.created_at)}</span>
                  <span>·</span>
                  <span>更新于 {formatRelativeTime(data.updated_at)}</span>
                </div>
          {data.status === "failed" && data.error_message && (
            <Card className="mt-4 border-destructive/50 bg-destructive/5">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 shrink-0 text-destructive" />
                  <div className="flex-1 space-y-2">
                    <div>
                      <p className="text-sm font-medium text-destructive">研究执行失败</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        错误信息：<code className="rounded bg-muted px-1 py-0.5 text-[10px]">{data.error_message}</code>
                      </p>
                    </div>
                    <Button size="sm" onClick={onStart} disabled={starting}>
                      <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                      重新执行（会自动 fallback 到 mock）
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

                          <div className="mt-3">
                  <TagSelector
                    researchId={data.id}
                    currentTags={data.tags || []}
                    onDetach={(tagId) => detachTag.mutate({ researchId: data.id, tagId })}
                  />
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">研究目标</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed">{data.goal}</p>
                </CardContent>
              </Card>

              {data.constraints && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">约束条件</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-relaxed text-muted-foreground">{data.constraints}</p>
                  </CardContent>
                </Card>
              )}

              {data.expected_output && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">预期输出</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-relaxed text-muted-foreground">{data.expected_output}</p>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Activity className="h-4 w-4" /> 执行
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {data.status === "pending" ? (
                    <div className="flex items-center gap-3">
                      <Button asChild>
                        <Link href={`/research/${data.id}/execute`}>开始研究</Link>
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        进入执行视图查看实时进度
                      </span>
                    </div>
                  ) : data.status === "running" ? (
                    <div className="flex items-center gap-3">
                      <Button asChild>
                        <Link href={`/research/${data.id}/execute`}>查看执行进度</Link>
                      </Button>
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">正在执行...</span>
                    </div>
                  ) : data.status === "completed" ? (
                    <div className="flex flex-wrap items-center gap-3">
                      <Button asChild>
                        <Link href={`/research/${data.id}/report`}>
                          <FileText className="mr-1.5 h-3.5 w-3.5" />
                          查看完整报告
                        </Link>
                      </Button>
                      <Button asChild variant="outline">
                        <Link href={`/research/${data.id}/history`}>
                          <History className="mr-1.5 h-3.5 w-3.5" />
                          版本历史
                        </Link>
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        重新执行可在报告页操作
                      </span>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">暂无执行状态。</p>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Sidebar */}
          <aside className="space-y-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">快速操作</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Button asChild variant="outline" className="w-full justify-start" size="sm">
                  <Link href={`/history/${data.id}`}>
                    <History className="mr-2 h-3.5 w-3.5" />
                    查看版本历史
                  </Link>
                </Button>
                {data.status === "completed" && (
                  <Button asChild variant="outline" className="w-full justify-start" size="sm">
                    <Link href={`/research/${data.id}/report`}>
                      <FileText className="mr-2 h-3.5 w-3.5" />
                      查看报告
                    </Link>
                  </Button>
                )}
                {data.status === "pending" && (
                  <Button asChild variant="outline" className="w-full justify-start" size="sm">
                    <Link href={`/research/${data.id}/execute`}>
                      <Activity className="mr-2 h-3.5 w-3.5" />
                      开始执行
                    </Link>
                  </Button>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                  小贴士
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-xs text-muted-foreground">
                <p>
                  使用 <strong className="text-foreground">标签</strong> 分类研究，便于在 /research 列表中筛选。
                </p>
                <p>
                  研究完成后，<strong className="text-foreground">报告</strong> 自动生成并归档到知识库。
                </p>
                <p>
                  <strong className="text-foreground">版本历史</strong> 保留每次重跑的快照，可 diff / fork / 回滚。
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                  元数据
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">ID</span>
                  <code className="font-mono text-[10px]">{data.id}</code>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">成本估算</span>
                  <span>${data.estimated_cost?.toFixed(2) || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">深度</span>
                  <span>{data.depth}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">优先级</span>
                  <span>{data.priority}</span>
                </div>
              </CardContent>
            </Card>
          </aside>
        </div>
      )}
    </div>
  );
}
