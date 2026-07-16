"use client";
import Link from "next/link";
import { Activity, ChevronRight, FlaskConical } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { formatRelativeTime } from "@/lib/utils";

interface ResearchLite {
  id: string;
  title: string;
  status: "pending" | "running" | "completed" | "failed";
  priority: "low" | "medium" | "high";
  depth: string;
  updated_at: string;
}

export function RunningSection({ items, loading }: { items?: ResearchLite[]; loading?: boolean }) {
  const running = (items ?? []).filter((r) => r.status === "running" || r.status === "pending");

  if (!loading && running.length === 0) return null;

  return (
    <Card className="border-info/30 bg-info/5">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4 animate-pulse text-info" />
          正在运行 ({running.length})
        </CardTitle>
        <Link href="/research?status=running" className="text-xs text-muted-foreground hover:text-foreground">
          查看全部
        </Link>
      </CardHeader>
      <CardContent className="space-y-1 p-2 pt-0">
        {loading ? (
          <div className="space-y-2 px-2 py-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : (
          running.map((r) => (
            <div
              key={r.id}
              className="group flex items-center gap-3 rounded-md bg-background/60 px-3 py-2.5 transition-colors hover:bg-background"
            >
              <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-info/10">
                <FlaskConical className="h-4 w-4 text-info" />
                <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-info">
                  <span className="absolute inset-0 animate-ping rounded-full bg-info opacity-75"></span>
                </span>
              </div>
              <div className="flex-1 overflow-hidden">
                <p className="truncate text-sm font-medium">{r.title}</p>
                <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="info" className="h-4 px-1 text-[10px]">
                    {r.status === "running" ? "执行中" : "待开始"}
                  </Badge>
                  <span>深度：{r.depth}</span>
                  <span>·</span>
                  <span>{formatRelativeTime(r.updated_at)}</span>
                </div>
              </div>
              <Button asChild size="sm" variant="default" className="h-8 gap-1.5 px-3">
                <Link href={`/research/${r.id}/execute`}>
                  <Activity className="h-3.5 w-3.5" />
                  进入执行
                </Link>
              </Button>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
