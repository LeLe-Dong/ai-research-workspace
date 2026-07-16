"use client";
import Link from "next/link";
import { BookOpen, ArrowUpRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { PopularKnowledge } from "@/lib/types";

export function PopularKnowledge({ items, loading }: { items?: PopularKnowledge[]; loading?: boolean }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="text-base">热门知识</CardTitle>
        <Link href="/knowledge" className="text-xs text-muted-foreground hover:text-foreground">
          浏览全部
        </Link>
      </CardHeader>
      <CardContent className="space-y-2 p-2 pt-0">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-md border p-3">
              <Skeleton className="h-3.5 w-3/4" />
              <Skeleton className="mt-1.5 h-3 w-full" />
            </div>
          ))
        ) : items && items.length > 0 ? (
          items.map((k) => (
            <Link
              key={k.id}
              href={`/knowledge/${k.id}`}
              className="group block rounded-md border p-3 transition-colors hover:bg-accent/30"
            >
              <div className="flex items-start gap-2">
                <BookOpen className="mt-0.5 h-3.5 w-3.5 text-muted-foreground" />
                <div className="flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium leading-tight">{k.title}</p>
                    <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  </div>
                  {k.excerpt && (
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{k.excerpt}</p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {k.tags.map((t) => (
                      <Badge key={t} variant="outline" className="h-4 px-1 text-[10px]">
                        {t}
                      </Badge>
                    ))}
                    <Badge variant="success" className="h-4 px-1 text-[10px]">
                      ★ {k.score.toFixed(1)}
                    </Badge>
                  </div>
                </div>
              </div>
            </Link>
          ))
        ) : (
          <p className="py-6 text-center text-sm text-muted-foreground">暂无归档研究。</p>
        )}
      </CardContent>
    </Card>
  );
}
