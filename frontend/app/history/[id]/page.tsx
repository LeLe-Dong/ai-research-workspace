"use client";
import { useParams } from "next/navigation";
import { useVersions, useFork, useRollback } from "@/features/history/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { GitBranch, RotateCcw, ArrowRight, ChevronRight, MessageSquare, History, Sparkles, Info } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const statusLabel: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
};

export default function 历史详情页() {
  const params = useParams();
  const researchId = params.id as string;
  const { data, isLoading } = useVersions(researchId);
  const fork = useFork();
  const rollback = useRollback();
  

  const handleFork = async (version: number) => {
      await fork.mutateAsync({ researchId, version });
    };

  const handleRollback = async (version: number) => {
    const msg = prompt(`回滚到 v${version} 将创建新版本，不会删除历史记录。确认？`);
    if (msg === null) return;
    try {
      await rollback.mutateAsync({ researchId, version, commitMessage: `Rollback to v${version}` });
    } catch (e) {
      // toast already in hook
    }
  };

  if (isLoading) {
    return (
      <div className="container max-w-none px-6 py-6">
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div>
            <div className="mb-6 h-8 w-48 animate-pulse rounded bg-muted" />
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <Card key={i} className="p-4">
                  <div className="h-4 w-full animate-pulse rounded bg-muted" />
                </Card>
              ))}
            </div>
          </div>
          <aside className="space-y-4">
            <Card><CardContent className="py-8 text-center text-xs text-muted-foreground">加载中...</CardContent></Card>
          </aside>
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="container max-w-none px-6 py-6">
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div>
            <p className="text-sm text-muted-foreground">暂无版本记录。</p>
            <Button asChild className="mt-4">
              <Link href={`/research/${researchId}`}>返回研究</Link>
            </Button>
          </div>
          <aside className="space-y-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Info className="h-3.5 w-3.5" />
                  什么是版本历史？
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-muted-foreground">
                <p>每次重新执行研究都会创建一个新版本快照。</p>
                <p>你可以对比版本、fork 新研究，或回滚到任一历史版本。</p>
              </CardContent>
            </Card>
          </aside>
        </div>
      </div>
    );
  }

  const completedCount = data.filter(v => v.status === "completed").length;
  const latestVersion = data[0];

  return (
    <div className="container max-w-none px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">版本历史</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            共 {data.length} 个版本 · {completedCount} 个已完成 · 点击版本查看详情或进行 fork
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href={`/research/${researchId}`}>
            <ArrowRight className="mr-1.5 h-3.5 w-3.5" />
            返回研究
          </Link>
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Main: timeline */}
        <div className="relative space-y-0">
          {data.map((v, idx) => (
            <div key={v.id} className="relative flex gap-4 pb-6">
              {/* Timeline line */}
              {idx < data.length - 1 && (
                <div className="absolute left-[11px] top-5 h-full w-px bg-border" />
              )}

              {/* Dot */}
              <div className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full border-2 bg-background"
                   style={{ borderColor: v.version === 1 ? "#10b981" : "#6366f1" }}>
                <span className="flex h-full w-full items-center justify-center text-[9px] font-bold">
                  {v.version}
                </span>
              </div>

              {/* Card */}
              <Card className="flex-1 p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">v{v.version}</span>
                      <Badge variant={v.status === "completed" ? "success" : v.status === "running" ? "info" : "secondary"}>
                        {statusLabel[v.status] || v.status}
                      </Badge>
                      {v.parent_version && (
                        <Badge variant="outline" className="text-xs">
                          <GitBranch className="mr-1 h-3 w-3" />
                          基于 v{v.parent_version}
                        </Badge>
                      )}
                      {v.version === 1 && (
                        <Badge variant="outline" className="text-xs">
                          初始版本
                        </Badge>
                      )}
                      {idx === 0 && (
                        <Badge variant="info" className="text-xs">
                          最新
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm font-medium">{v.title}</p>
                    {v.commit_message && (
                      <p className="flex items-center gap-1 text-xs text-muted-foreground">
                        <MessageSquare className="h-3 w-3" />
                        {v.commit_message}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {new Date(v.created_at).toLocaleString()}
                      {v.created_by && ` · by ${v.created_by}`}
                    </p>
                  </div>

                  <div className="flex items-center gap-1">
                    {v.version > 1 && (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleFork(v.version)}
                          disabled={fork.isPending}
                          title="基于此版本创建新研究"
                        >
                          <GitBranch className="mr-1.5 h-3.5 w-3.5" />
                          Fork
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRollback(v.version)}
                          disabled={rollback.isPending}
                          title="回滚到此版本"
                        >
                          <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                          回滚
                        </Button>
                      </>
                    )}
                    <Button asChild variant="ghost" size="icon" className="h-8 w-8" title="对比上一版本">
                      <Link href={`/history/${researchId}/diff?v1=${v.version}&v2=${Math.max(1, v.version - 1)}`}>
                        <ChevronRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  </div>
                </div>
              </Card>
            </div>
          ))}
        </div>

        {/* Sidebar */}
        <aside className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <History className="h-3.5 w-3.5 text-blue-500" />
                版本控制说明
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs text-muted-foreground">
              <p>
                每次重新执行研究都会创建一个<strong className="text-foreground">新版本快照</strong>，保留所有历史。
              </p>
              <p>
                <strong className="text-foreground">Fork</strong>：基于历史版本创建新研究，保留原始上下文。
              </p>
              <p>
                <strong className="text-foreground">回滚</strong>：回滚到任一历史版本（实际是创建新版本）。
              </p>
              <p>
                <strong className="text-foreground">对比</strong>：查看两个版本之间的差异。
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                最佳实践
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p>• 在修改目标或约束前先 fork</p>
              <p>• 用 commit message 记录每次重跑的原因</p>
              <p>• 定期对比历史版本，识别最优配置</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">最新版本</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">版本</span>
                <span className="font-mono">v{latestVersion.version}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">状态</span>
                <Badge variant={latestVersion.status === "completed" ? "success" : "secondary"}>
                  {statusLabel[latestVersion.status]}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">创建于</span>
                <span>{new Date(latestVersion.created_at).toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">by</span>
                <span>{latestVersion.created_by || "system"}</span>
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
