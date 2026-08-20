"use client";
import { useState } from "react";
import Link from "next/link";
import { FlaskConical, ChevronRight, Trash2, Loader2, Activity, Eye, Tag as TagIcon, X, Search } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime } from "@/lib/utils";
import { useResearchList, useDeleteResearch } from "../hooks";
import { useTags } from "@/features/tags/hooks";
import { toast } from "sonner";

interface ResearchListProps {
  searchQuery?: string;
}

const statusVariant = {
  pending: "secondary",
  running: "info",
  completed: "success",
  failed: "destructive",
} as const;

const priorityVariant = {
  low: "secondary",
  medium: "info",
  high: "warning",
} as const;

const statusLabel = {
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
};

const TAG_COLORS: Record<string, string> = {
  blue: "bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-300",
  green: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  red: "bg-red-500/15 text-red-700 border-red-500/30 dark:text-red-300",
  amber: "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
  purple: "bg-purple-500/15 text-purple-700 border-purple-500/30 dark:text-purple-300",
};

export function ResearchList({ searchQuery }: ResearchListProps) {
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const { data, isLoading } = useResearchList(selectedTag ?? undefined, searchQuery);
  const { data: allTags = [] } = useTags();
  const del = useDeleteResearch();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const onDelete = async (id: string, title: string) => {
    if (!confirm(`确定删除「${title}」？此操作不可撤销。`)) return;
    try {
      await del.mutateAsync(id);
      toast.success("研究已删除");
    } catch (err) {
      toast.error("删除失败", { description: (err as Error).message });
    }
  };

  const visibleTags = allTags.filter(t => t.count && t.count > 0).slice(0, 12);

  const hasFilter = selectedTag || searchQuery;
  const resultCount = data?.length ?? 0;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="text-base">
          {hasFilter ? `搜索结果（${resultCount} 项）` : "所有研究"}
        </CardTitle>
        <Button asChild size="sm">
          <Link href="/research/new">新建研究</Link>
        </Button>
      </CardHeader>

      {/* Search + Tag filter chips */}
      {(visibleTags.length > 0 || searchQuery) && (
        <div className="border-b px-4 py-2.5">
          <div className="flex items-center gap-2">
            {searchQuery && (
              <div className="flex items-center gap-1.5 rounded-full border bg-muted/50 px-2.5 py-1 text-xs">
                <Search className="h-3 w-3 text-muted-foreground" />
                <span className="text-muted-foreground">搜索：</span>
                <span className="font-medium">{searchQuery}</span>
              </div>
            )}
            <TagIcon className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">筛选：</span>
            <button
              onClick={() => setSelectedTag(null)}
              className={
                "rounded-full border px-2.5 py-0.5 text-xs transition-colors " +
                (selectedTag === null
                  ? "border-foreground bg-foreground text-background"
                  : "border-border bg-background hover:bg-muted")
              }
            >
              全部
            </button>
            {visibleTags.map(t => (
              <button
                key={t.id}
                onClick={() => setSelectedTag(t.name === selectedTag ? null : t.name)}
                className={
                  "rounded-full border px-2.5 py-0.5 text-xs transition-colors " +
                  (selectedTag === t.name
                    ? TAG_COLORS[t.color] || TAG_COLORS.blue
                    : "border-border bg-background hover:bg-muted text-muted-foreground")
                }
              >
                {t.name}
                <span className="ml-1 opacity-60">{t.count}</span>
              </button>
            ))}
            {selectedTag && (
              <button
                onClick={() => setSelectedTag(null)}
                className="ml-1 flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-muted/70"
              >
                <X className="h-2.5 w-2.5" /> 清除
              </button>
            )}
          </div>
        </div>
      )}

      <CardContent className="p-0">
        {isLoading ? (
          <div className="space-y-1 p-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-2 py-2.5">
                <Skeleton className="h-8 w-8 rounded-md" />
                <div className="flex-1 space-y-1">
                  <Skeleton className="h-3.5 w-3/4" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </div>
            ))}
          </div>
        ) : data && data.length > 0 ? (
          <>
            {hasFilter && (
              <div className="border-b bg-muted/30 px-4 py-1.5 text-[10px] text-muted-foreground">
                共 {resultCount} 个匹配结果
                {searchQuery && <span> · 关键词「{searchQuery}」</span>}
                {selectedTag && <span> · 标签「{selectedTag}」</span>}
              </div>
            )}
            <ul className="divide-y">
              {data.map((r) => {
                const rTags = r.tags || [];
                return (
                  <li key={r.id}>
                    <div className="group flex items-center gap-3 px-4 py-3 hover:bg-accent/30">
                      <Link href={`/research/${r.id}`} className="flex flex-1 items-center gap-3">
                        <div className={"relative flex h-8 w-8 shrink-0 items-center justify-center rounded-md " + (r.status === "running" ? "bg-info/10" : "bg-muted")}>
                          <FlaskConical className={"h-4 w-4 " + (r.status === "running" ? "text-info" : "text-muted-foreground")} />
                          {(r.status === "running" || r.status === "pending") && (
                            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-info">
                              <span className="absolute inset-0 animate-ping rounded-full bg-info opacity-75"></span>
                            </span>
                          )}
                        </div>
                        <div className="flex-1 overflow-hidden">
                          <p className="truncate text-sm font-medium">{r.title}</p>
                          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                            <Badge variant={statusVariant[r.status]} className="h-4 px-1 text-[10px]">
                              {statusLabel[r.status]}
                            </Badge>
                            <Badge variant={priorityVariant[r.priority]} className="h-4 px-1 text-[10px]">
                              {r.priority}
                            </Badge>
                            <Badge variant="outline" className="h-4 px-1 text-[10px]">
                              {r.depth}
                            </Badge>
                            {rTags.slice(0, 3).map((t: { id: string; name: string; color: string }) => (
                              <Badge
                                key={t.id}
                                variant="outline"
                                className={`h-4 px-1 text-[10px] ${TAG_COLORS[t.color] || TAG_COLORS.blue}`}
                              >
                                {t.name}
                              </Badge>
                            ))}
                            {rTags.length > 3 && (
                              <span className="text-[10px]">+{rTags.length - 3}</span>
                            )}
                            <span>{formatRelativeTime(r.updated_at)}</span>
                            {r.score !== null && (
                              <Badge variant="success" className="h-4 px-1 text-[10px]">
                                ★ {r.score.toFixed(1)}
                              </Badge>
                            )}
                          </div>
                        </div>
                        <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100" />
                      </Link>
                      {(r.status === "running" || r.status === "pending") && (
                        <Button asChild size="sm" variant="default" className="h-7 gap-1 px-2.5 text-xs">
                          <Link href={`/research/${r.id}/execute`}>
                            <Activity className="h-3 w-3" />
                            执行中
                          </Link>
                        </Button>
                      )}
                      {(r.status === "completed" || r.status === "failed") && (
                        <Button
                          asChild
                          size="sm"
                          variant="outline"
                          className="h-7 gap-1 px-2.5 text-xs"
                          title="查看该次作业的执行快照"
                        >
                          <Link href={`/research/${r.id}/execute`}>
                            <Eye className="h-3 w-3" />
                            查看运行详情
                          </Link>
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 opacity-0 group-hover:opacity-100"
                        onClick={() => onDelete(r.id, r.title)}
                        disabled={deletingId === r.id}
                      >
                        {deletingId === r.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                        )}
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        ) : (
          <div className="px-4 py-12 text-center">
            <FlaskConical className="mx-auto h-8 w-8 text-muted-foreground/50" />
            <p className="mt-3 text-sm font-medium">
              {hasFilter ? "未找到匹配的研究" : "暂无研究"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {hasFilter ? "试试调整搜索关键词或清除筛选条件" : "点击「新建研究」开始第一个研究项目。"}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
