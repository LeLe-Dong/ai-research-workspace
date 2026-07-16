"use client";
import Link from "next/link";
import { useHistoryList } from "../hooks";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowRight, GitBranch } from "lucide-react";

export function HistoryList() {
  const { data, isLoading } = useHistoryList() as { data: any[] | undefined; isLoading: boolean };

  if (isLoading) {
    return (
      <div className="grid gap-4">
        {[...Array(5)].map((_, i) => (
          <Card key={i} className="p-4">
            <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
          </Card>
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        暂无研究历史。创建你的第一个研究项目开始吧。
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {data.map((item) => (
        <Card key={item.id} className="p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <Link href={`/research/${item.id}`} className="font-medium hover:underline">
                  {item.title}
                </Link>
                <Badge variant={item.status === "completed" ? "success" : item.status === "running" ? "info" : "secondary"}>
                  {item.status}
                </Badge>
              </div>
              <p className="line-clamp-1 text-sm text-muted-foreground">{item.goal}</p>
              <p className="text-xs text-muted-foreground">
                深度：{item.depth} · Priority：{item.priority} · 更新时间：{new Date(item.updated_at).toLocaleString()}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button asChild variant="ghost" size="sm">
                <Link href={`/history/${item.id}`}>
                  <GitBranch className="mr-1.5 h-3.5 w-3.5" />
                  版本历史
                </Link>
              </Button>
              <Button asChild variant="ghost" size="sm">
                <Link href={`/research/${item.id}`}>
                  <ArrowRight className="mr-1.5 h-3.5 w-3.5" />
                  查看
                </Link>
              </Button>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
