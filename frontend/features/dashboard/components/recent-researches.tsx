"use client";
import Link from "next/link";
import { ChevronRight, FlaskConical, Activity, Eye } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime } from "@/lib/utils";
import type { RecentResearch } from "@/lib/types";

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

export function RecentResearches({ items, loading }: { items?: RecentResearch[]; loading?: boolean }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="text-base">最近研究</CardTitle>
        <Link href="/research" className="text-xs text-muted-foreground hover:text-foreground">
          查看全部
        </Link>
      </CardHeader>
      <CardContent className="space-y-1 p-2 pt-0">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-2 py-2.5">
              <Skeleton className="h-8 w-8 rounded-md" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-3.5 w-3/4" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            </div>
          ))
        ) : items && items.length > 0 ? (
          items.map((r) => {
            const isRunning = r.status === "running" || r.status === "pending";
            return (
              <div
                key={r.id}
                className={
                  "group flex items-center gap-3 rounded-md px-2 py-2.5 transition-colors " +
                  (isRunning ? "bg-info/5 hover:bg-info/10" : "hover:bg-accent/50")
                }
              >
                <Link href={`/research/${r.id}`} className="flex flex-1 items-center gap-3 overflow-hidden">
                  <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted">
                    <FlaskConical className="h-4 w-4 text-muted-foreground" />
                    {isRunning && (
                      <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-info">
                        <span className="absolute inset-0 animate-ping rounded-full bg-info opacity-75"></span>
                      </span>
                    )}
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <p className="truncate text-sm font-medium">{r.title}</p>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                      <Badge variant={statusVariant[r.status]} className="h-4 px-1 text-[10px]">
                        {r.status}
                      </Badge>
                      <Badge variant={priorityVariant[r.priority]} className="h-4 px-1 text-[10px]">
                        {r.priority}
                      </Badge>
                      <span>{formatRelativeTime(r.updated_at)}</span>
                    </div>
                  </div>
                </Link>
                {isRunning ? (
                  <Button asChild size="sm" variant="default" className="h-7 gap-1 px-2.5 text-xs">
                    <Link href={`/research/${r.id}/execute`}>
                      <Activity className="h-3 w-3" />
                      进入执行
                    </Link>
                  </Button>
                ) : (
                  <Button
                    asChild
                    size="sm"
                    variant="outline"
                    className="h-7 gap-1 px-2.5 text-xs opacity-0 transition-opacity group-hover:opacity-100"
                    title="查看该次作业的执行快照"
                  >
                    <Link href={`/research/${r.id}/execute`}>
                      <Eye className="h-3 w-3" />
                      查看运行详情
                    </Link>
                  </Button>
                )}
              </div>
            );
          })
        ) : (
          <p className="px-2 py-8 text-center text-sm text-muted-foreground">暂无研究。</p>
        )}
      </CardContent>
    </Card>
  );
}
