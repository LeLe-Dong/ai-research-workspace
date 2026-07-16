"use client";
import { useEffect, useRef } from "react";
import {
  Search, FileSearch, BookOpen, BarChart3, ListChecks,
  Sparkles, FileText, Loader2, AlertTriangle, CheckCircle2,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import type { TimelineEventOut } from "@/lib/types";

const PHASE_ICON: Record<string, typeof Search> = {
  understand: Sparkles,
  decompose: ListChecks,
  search: Search,
  read: BookOpen,
  analyze: BarChart3,
  derive: Sparkles,
  summarize: FileText,
  comparison: BarChart3,
  evaluation: ListChecks,
  report: FileText,
  requirement: ListChecks,
  research: Search,
  review: CheckCircle2,
};

const PHASE_COLOR: Record<string, string> = {
  understand: "text-purple-500 bg-purple-500/10",
  decompose: "text-blue-500 bg-blue-500/10",
  search: "text-cyan-500 bg-cyan-500/10",
  read: "text-indigo-500 bg-indigo-500/10",
  analyze: "text-amber-500 bg-amber-500/10",
  derive: "text-pink-500 bg-pink-500/10",
  summarize: "text-emerald-500 bg-emerald-500/10",
  review: "text-emerald-600 bg-emerald-500/15",
};

function timeOf(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}

export function TimelineStream({ events }: { events?: TimelineEventOut[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Auto-scroll to bottom on new events
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [events?.length]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          时间线
        </p>
        <p className="mt-0.5 text-[10px] text-muted-foreground">
          智能体实时执行 · {events?.length ?? 0} 个事件
        </p>
      </div>

      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="space-y-2 p-3">
          {!events ? (
            <div className="flex items-center gap-2 px-2 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              等待智能体...
            </div>
          ) : events.length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted-foreground">暂无事件。</p>
          ) : (
            events.map((e) => {
              const Icon = PHASE_ICON[e.phase] || Sparkles;
              const color = PHASE_COLOR[e.phase] || "text-muted-foreground bg-muted";
              const isError = e.level === "error";
              const isSuccess = e.level === "success";

              return (
                <div
                  key={e.id}
                  className={
                    "flex gap-2.5 rounded-md border px-2.5 py-2 transition-colors " +
                    (isError
                      ? "border-destructive/50 bg-destructive/5"
                      : isSuccess
                      ? "border-emerald-500/30 bg-emerald-500/5"
                      : "bg-card")
                  }
                >
                  <div className={"flex h-6 w-6 shrink-0 items-center justify-center rounded-full " + color}>
                    {isError ? (
                      <AlertTriangle className="h-3 w-3" />
                    ) : (
                      <Icon className="h-3 w-3" />
                    )}
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="truncate text-xs font-medium">{e.title}</p>
                      <span className="shrink-0 font-mono text-[9px] text-muted-foreground">
                        {timeOf(e.ts)}
                      </span>
                    </div>
                    {e.detail && (
                      <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                        {e.detail}
                      </p>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
