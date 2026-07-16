"use client";
import { FlaskConical, CheckCircle2, TrendingUp, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardStats } from "@/lib/types";

const cards = [
  { key: "total", label: "研究总数", icon: FlaskConical, accent: "text-blue-500" },
  { key: "today", label: "今日完成", icon: CheckCircle2, accent: "text-emerald-500" },
  { key: "running", label: "执行中", icon: Sparkles, accent: "text-purple-500" },
  { key: "score", label: "平均评分", icon: TrendingUp, accent: "text-amber-500" },
] as const;

export function StatsGrid({ stats, loading }: { stats?: DashboardStats; loading?: boolean }) {
  const values: Record<string, string> = stats
    ? {
        total: String(stats.total_researches),
        today: String(stats.today_completed),
        running: String(stats.running),
        score: stats.average_score.toFixed(1),
      }
    : {};

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 max-w-4xl">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <Card key={c.key}>
            <CardContent className="flex items-center gap-3 p-4">
              <div className={`flex h-9 w-9 items-center justify-center rounded-md bg-muted ${c.accent}`}>
                <Icon className="h-4 w-4" />
              </div>
              <div className="flex-1">
                <p className="text-xs text-muted-foreground">{c.label}</p>
                {loading ? (
                  <Skeleton className="mt-1 h-6 w-12" />
                ) : (
                  <p className="text-xl font-semibold tracking-tight">{values[c.key] ?? "—"}</p>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
