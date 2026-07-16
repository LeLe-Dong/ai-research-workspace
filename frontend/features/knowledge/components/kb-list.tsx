"use client";
import Link from "next/link";
import { BookOpen, ChevronRight, Sparkles } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";

import { useCompletedResearches } from "@/features/research/hooks-report";
import { useState } from "react";
import { formatRelativeTime } from "@/lib/utils";

export function KnowledgeList() {
  const { data, isLoading } = useCompletedResearches();
  const [q, setQ] = useState("");

  const filtered = (data ?? []).filter((r) => {
    if (!q) return true;
    const hay = (r.title + " " + r.goal + " " + r.priority + " " + r.depth).toLowerCase();
    return hay.includes(q.toLowerCase());
  });

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">知识库</CardTitle>
          <Badge variant="outline" className="h-5 text-xs">{data?.length ?? 0} 归档</Badge>
        </div>
        <Input
          placeholder="Search 归档 research..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="h-8"
        />
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="space-y-1 p-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : filtered.length > 0 ? (
          <ul className="divide-y">
            {filtered.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/knowledge/${r.id}`}
                  className="group flex items-start gap-3 px-4 py-3 transition-colors hover:bg-accent/30"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
                    <BookOpen className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <p className="truncate text-sm font-medium">{r.title}</p>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{r.goal}</p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <Badge variant="outline" className="h-4 px-1 text-[10px]">{r.depth}</Badge>
                      <Badge variant="outline" className="h-4 px-1 text-[10px]">{r.priority}</Badge>
                      {r.score !== null && (
                        <Badge variant="success" className="h-4 px-1 text-[10px]">★ {r.score.toFixed(1)}</Badge>
                      )}
                      <span className="text-[10px] text-muted-foreground">{formatRelativeTime(r.updated_at)}</span>
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="px-4 py-12 text-center">
            <Sparkles className="mx-auto h-8 w-8 text-muted-foreground/40" />
            <p className="mt-3 text-sm font-medium">No 归档 research yet</p>
            <p className="mt-1 text-xs text-muted-foreground">完成一项研究即可填充此视图。</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
