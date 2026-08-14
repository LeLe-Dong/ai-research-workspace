"use client";
import { useEffect, useMemo, useRef, useState, memo } from "react";
import {
  Search, FileSearch, BookOpen, BarChart3, ListChecks,
  Sparkles, FileText, Loader2, AlertTriangle, CheckCircle2,
  Server, Filter,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import type { TimelineEventOut, TaskNode } from "@/lib/types";

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

const PHASE_COLORS_CHIP: Record<string, string> = {
  requirement: "bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-300",
  research: "bg-indigo-500/15 text-indigo-700 border-indigo-500/30 dark:text-indigo-300",
  comparison: "bg-purple-500/15 text-purple-700 border-purple-500/30 dark:text-purple-300",
  evaluation: "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
  report: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  validation: "bg-cyan-500/15 text-cyan-700 border-cyan-500/30 dark:text-cyan-300",
};

function timeOf(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}

type FilterMode = "all" | "k8s" | "errors";

function isK8sRelated(ev: TimelineEventOut): boolean {
  const s = `${ev.title ?? ""} ${ev.detail ?? ""} ${ev.phase ?? ""}`.toLowerCase();
  return s.includes("kubectl") ||
    s.includes("kube") ||
    s.includes("k8s") ||
    s.includes("kubernetes") ||
    s.includes("cluster") ||
    s.includes("cluster-admin") ||
    s.includes("pod ") ||
    s.includes("deployment") ||
    s.includes("replicaset") ||
    s.includes("validate") ||
    ev.phase === "validate";
}

// Memoized event card — only re-renders when its own data changes
const EventCard = memo(function EventCard({
  e,
  onClick,
  taskName,
  isSelected,
}: {
  e: TimelineEventOut;
  onClick?: (e: TimelineEventOut) => void;
  taskName?: string;
  isSelected?: boolean;
}) {
  const Icon = PHASE_ICON[e.phase] || Sparkles;
  const color = PHASE_COLOR[e.phase] || "text-muted-foreground bg-muted";
  const isError = e.level === "error";
  const isSuccess = e.level === "success";
  const taskChipClass = taskName
    ? PHASE_COLORS_CHIP[
        e.phase && PHASE_COLORS_CHIP[e.phase] ? e.phase : "research"
      ]
    : "";

  return (
    <button
      type="button"
      onClick={() => onClick?.(e)}
      className={
        "flex w-full gap-2.5 rounded-md border px-2.5 py-2 text-left transition-colors cursor-pointer " +
        (isSelected
          ? "border-primary bg-primary/10 ring-1 ring-primary/40 "
          : "hover:border-primary/40 hover:bg-accent/30 ") +
        (isError
          ? "border-destructive/50 bg-destructive/5"
          : isSuccess
            ? "border-emerald-500/30 bg-emerald-500/5"
            : "bg-card")
      }
      style={{ contentVisibility: "auto", containIntrinsicSize: "40px" }}
      title={e.task_id ? "点击过滤控制台到此任务" : "此事件未关联任务"}
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
          <div className="flex min-w-0 items-center gap-1.5">
            <p className="text-xs font-medium break-words">{e.title}</p>
            {taskName && (
              <span className={cn(
                "shrink-0 max-w-[100px] truncate rounded border px-1 py-0 text-[9px]",
                taskChipClass
              )}>
                {taskName}
              </span>
            )}
          </div>
          <span className="shrink-0 font-mono text-[9px] text-muted-foreground tabular-nums">
            {timeOf(e.ts)}
          </span>
        </div>
        {e.detail && (
          <p className="mt-0.5 line-clamp-3 whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-muted-foreground">
            {e.detail}
          </p>
        )}
      </div>
    </button>
  );
});

import { cn } from "@/lib/utils";

export function TimelineStream({
  events,
  tasks,
  onSelectTask,
  selectedTaskId,
}: {
  events?: TimelineEventOut[];
  tasks?: TaskNode[];
  /** Optional callback when a Timeline event is clicked: passes event.task_id (may be null). */
  onSelectTask?: (taskId: string | null) => void;
  /** Currently selected task (for visual highlight). */
  selectedTaskId?: string | null;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState<FilterMode>("all");

  const filtered = useMemo(() => {
    if (!events) return [];
    if (filter === "all") return events;
    if (filter === "errors") return events.filter((e) => e.level === "error" || e.level === "warn");
    if (filter === "k8s") return events.filter(isK8sRelated);
    return events;
  }, [events, filter]);

  const counts = useMemo(() => {
    const all = events?.length ?? 0;
    const k8s = events ? events.filter(isK8sRelated).length : 0;
    const errs = events ? events.filter((e) => e.level === "error" || e.level === "warn").length : 0;
    return { all, k8s, errs };
  }, [events]);

  // task id → name lookup for chip rendering
  const taskNameById = useMemo(() => {
    const m: Record<string, string> = {};
    (tasks ?? []).forEach((t) => { m[t.id] = t.name; });
    return m;
  }, [tasks]);

  // Auto-scroll to bottom on new events (throttled via rAF)
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const raf = requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
    return () => cancelAnimationFrame(raf);
  }, [filtered.length]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            时间线
          </p>
          <span className="font-mono text-[10px] text-muted-foreground">
            {filtered.length} / {events?.length ?? 0}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-1.5">
          <Filter className="h-3 w-3 text-muted-foreground" />
          <button
            onClick={() => setFilter("all")}
            className={
              "h-5 rounded-full border px-2 text-[10px] transition-colors " +
              (filter === "all"
                ? "border-foreground bg-foreground text-background"
                : "border-border bg-background hover:bg-muted text-muted-foreground")
            }
          >
            全部 {counts.all}
          </button>
          <button
            onClick={() => setFilter("k8s")}
            className={
              "h-5 rounded-full border px-2 text-[10px] transition-colors " +
              (filter === "k8s"
                ? "border-cyan-500 bg-cyan-500/15 text-cyan-700 dark:text-cyan-300"
                : "border-border bg-background hover:bg-muted text-muted-foreground")
            }
            title="筛选 kubectl / k8s / cluster / pod / deployment / validate 相关事件"
          >
            <Server className="mr-1 inline-block h-2.5 w-2.5" />
            K8s 验证 {counts.k8s}
          </button>
          <button
            onClick={() => setFilter("errors")}
            className={
              "h-5 rounded-full border px-2 text-[10px] transition-colors " +
              (filter === "errors"
                ? "border-destructive bg-destructive/15 text-destructive"
                : "border-border bg-background hover:bg-muted text-muted-foreground")
            }
            title="筛选错误 / 警告事件"
          >
            <AlertTriangle className="mr-1 inline-block h-2.5 w-2.5" />
            错误 {counts.errs}
          </button>
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground">
          点击节点 → 控制台过滤此任务的全部 trace
        </p>
      </div>

      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="space-y-2 p-3">
          {!events ? (
            <div className="flex items-center gap-2 px-2 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              等待智能体...
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-2 py-4 text-center text-xs text-muted-foreground">
              {filter === "all"
                ? "暂无事件。"
                : filter === "k8s"
                  ? "此研究未触发 K8s 验证阶段。"
                  : "此研究无错误 / 警告事件。"}
            </div>
          ) : (
            filtered.map((e) => (
              <EventCard
                key={e.id}
                e={e}
                onClick={(ev) => onSelectTask?.(ev.task_id ?? null)}
                taskName={e.task_id ? taskNameById[e.task_id] : undefined}
                isSelected={!!e.task_id && e.task_id === selectedTaskId}
              />
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
