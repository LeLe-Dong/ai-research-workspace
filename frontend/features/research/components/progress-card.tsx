"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  ListChecks,
} from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";
import type { ResearchProgress } from "../api-summary";

interface ProgressCardProps {
  summary?: ResearchProgress;
  loading?: boolean;
}

/**
 * Aggregated progress view for a single research.
 *
 * Surfaces:
 *  - tasks progress (N/N, percent)
 *  - timeline events count + duration span
 *  - coverage_gaps — explicit list of what's missing/incomplete (the killer
 *    feature for failed / crashed researches)
 */
export function ProgressCard({ summary, loading }: ProgressCardProps) {
  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="h-4 w-4 animate-spin" />
            执行进度
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="h-2 w-full animate-pulse rounded bg-muted" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-muted" />
        </CardContent>
      </Card>
    );
  }
  if (!summary) return null;

  const isRunning = summary.status === "running" || summary.status === "pending";
  const hasGaps = summary.coverage_gaps.length > 0;

  const durationStr = formatDuration(summary.duration_sec);
  const timelineGapStr = formatDuration(summary.progress_timeline_gap_sec);
  const firstTs = summary.progress_timeline_first
    ? new Date(summary.progress_timeline_first).toLocaleString("zh-CN")
    : null;
  const lastTs = summary.progress_timeline_last
    ? new Date(summary.progress_timeline_last).toLocaleString("zh-CN")
    : null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          {isRunning ? (
            <Loader2 className="h-4 w-4 animate-spin text-info" />
          ) : hasGaps ? (
            <AlertTriangle className="h-4 w-4 text-warning" />
          ) : summary.status === "completed" ? (
            <CheckCircle2 className="h-4 w-4 text-success" />
          ) : (
            <Clock className="h-4 w-4 text-muted-foreground" />
          )}
          执行进度
          {isRunning && (
            <Badge variant="info" className="h-4 px-1.5 text-[10px]">
              自动刷新中
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Tasks progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">子任务</span>
            <span className="font-mono">
              {summary.progress_tasks_done} / {summary.progress_tasks_total}
            </span>
          </div>
          <Progress value={summary.progress_tasks_pct} />
        </div>

        {/* Timeline metrics */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-muted-foreground">Timeline 事件</div>
            <div className="mt-0.5 font-mono">{summary.progress_timeline_events}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Timeline 跨度</div>
            <div className="mt-0.5 font-mono">{timelineGapStr}</div>
          </div>
          <div>
            <div className="text-muted-foreground">总耗时</div>
            <div className="mt-0.5 font-mono">{durationStr}</div>
          </div>
          <div>
            <div className="text-muted-foreground">报告版本</div>
            <div className="mt-0.5 font-mono">
              {summary.versions_count} ({summary.report_length_chars} 字符)
            </div>
          </div>
        </div>

        {/* Timestamps */}
        {firstTs && lastTs && (
          <div className="rounded-md bg-muted/40 p-2 text-[11px] leading-relaxed">
            <div className="text-muted-foreground">Timeline 首条 / 末条</div>
            <div className="mt-0.5 font-mono text-[10px]">{firstTs}</div>
            <div className="font-mono text-[10px]">{lastTs}</div>
          </div>
        )}

        {/* Coverage gaps — the bit that makes failed researches diagnosable */}
        {hasGaps && (
          <div className="rounded-md border border-warning/50 bg-warning/5 p-3">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-warning">
              <ListChecks className="h-3.5 w-3.5" />
              进度问题 ({summary.coverage_gaps.length})
            </div>
            <ul className="space-y-1.5 text-[11px] leading-relaxed">
              {summary.coverage_gaps.map((gap, i) => (
                <li
                  key={i}
                  className="flex items-start gap-1.5 text-muted-foreground"
                >
                  <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-warning" />
                  <span>{gap}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m${s > 0 ? ` ${s}s` : ""}`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h${m > 0 ? ` ${m}m` : ""}`;
}