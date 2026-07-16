"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Terminal, Loader2, CheckCircle2, AlertTriangle, Info,
  ChevronDown, ChevronRight, Copy, Download, Pause, Play, Filter, X,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { TimelineEventOut, ResearchStatus } from "@/lib/types";

type LogLevel = "info" | "success" | "warn" | "error";

function levelIcon(level: LogLevel) {
  if (level === "success") return <CheckCircle2 className="h-3 w-3 text-emerald-500" />;
  if (level === "error") return <AlertTriangle className="h-3 w-3 text-destructive" />;
  if (level === "warn") return <AlertTriangle className="h-3 w-3 text-amber-500" />;
  return <Info className="h-3 w-3 text-blue-400" />;
}

function levelClass(level: LogLevel) {
  if (level === "success") return "text-emerald-400";
  if (level === "error") return "text-destructive";
  if (level === "warn") return "text-amber-400";
  return "text-blue-400";
}

function fmt(ts: string) {
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

const LEVEL_LABELS: Record<LogLevel, string> = {
  info: "INFO",
  success: "OK",
  warn: "WARN",
  error: "ERR",
};

export function Console({
  events,
  status,
}: {
  events?: TimelineEventOut[];
  status?: ResearchStatus;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const [filterLevels, setFilterLevels] = useState<Set<LogLevel>>(
    new Set(["info", "success", "warn", "error"])
  );
  const [filterPhase, setFilterPhase] = useState<string>("");
  const [copied, setCopied] = useState(false);

  // Filtered events
  const filteredEvents = useMemo(() => {
    if (!events) return [];
    return events.filter((e) => {
      const level = (["info", "success", "warn", "error"].includes(e.level) ? e.level : "info") as LogLevel;
      if (!filterLevels.has(level)) return false;
      if (filterPhase && !e.phase.includes(filterPhase)) return false;
      return true;
    });
  }, [events, filterLevels, filterPhase]);

  // Auto-scroll to bottom when new events arrive (if enabled)
  useEffect(() => {
    if (!autoScroll) return;
    const el = containerRef.current;
    if (!el) return;
    // Use rAF to ensure layout settled
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [filteredEvents.length, autoScroll]);

  // Detect manual scroll up — pause auto-scroll
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      // If user scrolled up by > 50px, pause auto-scroll
      if (distanceFromBottom > 50 && autoScroll) {
        setAutoScroll(false);
      }
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, [autoScroll]);

  const isRunning = status === "running";
  const totalEvents = events?.length ?? 0;
  const visibleCount = filteredEvents.length;
  const errCount = events?.filter((e) => e.level === "error").length ?? 0;
  const warnCount = events?.filter((e) => e.level === "warn").length ?? 0;
  const elapsed = events && events.length > 0
    ? Math.round((new Date(events[events.length - 1].ts).getTime() - new Date(events[0].ts).getTime()) / 100) / 10
    : 0;

  // Estimate tokens from total events (rough)
  const tokenEstimate = events ? Math.round(events.reduce((acc, e) => acc + (e.title?.length ?? 0) + (e.detail?.length ?? 0), 0) / 4) : 0;

  const toggleExpanded = (id: string) => {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id); else next.add(id);
    setExpanded(next);
  };

  const toggleLevel = (level: LogLevel) => {
    const next = new Set(filterLevels);
    if (next.has(level)) next.delete(level); else next.add(level);
    setFilterLevels(next);
  };

  const exportLogs = () => {
    if (!events) return;
    const lines = events.map(
      (e) => `[${fmt(e.ts)}] [${e.phase.padEnd(10)}] ${(LEVEL_LABELS[(e.level as LogLevel)] ?? "INFO").padEnd(4)} ${e.title}${e.detail ? "\n    " + e.detail : ""}`
    );
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `research-log-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyAll = async () => {
    if (!events) return;
    const lines = events.map(
      (e) => `[${fmt(e.ts)}] [${e.phase.padEnd(10)}] ${(LEVEL_LABELS[(e.level as LogLevel)] ?? "INFO").padEnd(4)} ${e.title}${e.detail ? "\n    " + e.detail : ""}`
    );
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {}
  };

  // Unique phases for filter
  const phases = useMemo(() => {
    if (!events) return [];
    return Array.from(new Set(events.map((e) => e.phase)));
  }, [events]);

  return (
    <div className="flex h-full flex-col bg-zinc-950 font-mono text-xs">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 bg-zinc-900 px-3 py-1">
        <div className="flex shrink-0 items-center gap-2">
          <Terminal className="h-3 w-3 text-zinc-500" />
          <span className="text-zinc-400">控制台</span>
          {isRunning && <Loader2 className="h-3 w-3 animate-spin text-blue-400" />}
        </div>

        <div className="flex shrink-0 items-center gap-2 text-[10px] text-zinc-500">
          <span>事件：{visibleCount}/{totalEvents}</span>
          {warnCount > 0 && <span className="text-amber-400">W:{warnCount}</span>}
          {errCount > 0 && <span className="text-destructive">E:{errCount}</span>}
          <span>{elapsed.toFixed(1)}s</span>
          <span className="text-zinc-600">~{tokenEstimate} tok</span>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-1 border-b border-zinc-800 bg-zinc-900/60 px-3 py-1 text-[10px]">
        <Filter className="h-3 w-3 text-zinc-500" />
        {(["info", "success", "warn", "error"] as LogLevel[]).map((lvl) => (
          <button
            key={lvl}
            type="button"
            onClick={() => toggleLevel(lvl)}
            className={cn(
              "px-1.5 py-0.5 rounded transition-colors",
              filterLevels.has(lvl)
                ? levelClass(lvl) + " bg-zinc-800"
                : "text-zinc-600 bg-zinc-900 line-through"
            )}
            title={lvl}
          >
            {LEVEL_LABELS[lvl]}
          </button>
        ))}
        {phases.length > 1 && (
          <>
            <span className="mx-1 text-zinc-600">|</span>
            <select
              value={filterPhase}
              onChange={(e) => setFilterPhase(e.target.value)}
              className="bg-zinc-900 px-1 py-0.5 text-[10px] text-zinc-400 outline-none rounded"
            >
              <option value="">全部 phase</option>
              {phases.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={copyAll}
            className="h-5 px-1.5 text-[10px] text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            title="复制所有日志"
          >
            {copied ? <CheckCircle2 className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
            <span className="ml-0.5">{copied ? "已复制" : "复制"}</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={exportLogs}
            className="h-5 px-1.5 text-[10px] text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            title="导出日志为 .txt"
          >
            <Download className="h-3 w-3" />
            <span className="ml-0.5">.txt</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setAutoScroll(!autoScroll)}
            className="h-5 px-1.5 text-[10px] hover:bg-zinc-800"
            title={autoScroll ? "暂停自动滚动" : "恢复自动滚动"}
            disabled={!isRunning}
          >
            {autoScroll ? (
              <><Pause className="h-3 w-3 text-emerald-500" /><span className="ml-0.5 text-emerald-500">跟随</span></>
            ) : (
              <><Play className="h-3 w-3 text-zinc-400" /><span className="ml-0.5 text-zinc-400">已暂停</span></>
            )}
          </Button>
        </div>
      </div>

      {/* Log lines */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto"
      >
        {filteredEvents.length > 0 ? (
          <div className="space-y-px p-2">
            {filteredEvents.map((e) => {
              const isOpen = expanded.has(e.id);
              const level = (["info", "success", "warn", "error"].includes(e.level) ? e.level : "info") as LogLevel;
              const hasDetail = !!e.detail && e.detail.length > 0;
              return (
                <div key={e.id} className="group">
                  <button
                    type="button"
                    onClick={() => hasDetail && toggleExpanded(e.id)}
                    className={cn(
                      "flex w-full gap-2 rounded px-1 py-0.5 text-left hover:bg-zinc-900/70",
                      hasDetail && "cursor-pointer"
                    )}
                  >
                    <span className="shrink-0 text-zinc-600">{fmt(e.ts)}</span>
                    <span className="shrink-0 w-20 truncate text-zinc-500">[{e.phase}]</span>
                    <span className={cn("shrink-0 w-12 flex items-center gap-1", levelClass(level))}>
                      {levelIcon(level)}
                      {LEVEL_LABELS[level]}
                    </span>
                    <span className="flex-1 truncate text-zinc-300">{e.title}</span>
                    {hasDetail && (
                      <span className="shrink-0 text-zinc-600">
                        {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      </span>
                    )}
                  </button>
                  {hasDetail && isOpen && (
                    <div className="ml-7 mr-2 mb-1 rounded border-l-2 border-blue-500/30 bg-zinc-900/60 px-2 py-1 text-zinc-500">
                      <pre className="whitespace-pre-wrap break-all font-mono text-[10px]">{e.detail}</pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="px-3 py-3 text-zinc-600">// 等待智能体...</p>
        )}
        {!autoScroll && filteredEvents.length > 0 && (
          <div className="sticky bottom-2 flex justify-center">
            <button
              type="button"
              onClick={() => {
                setAutoScroll(true);
                const el = containerRef.current;
                if (el) el.scrollTop = el.scrollHeight;
              }}
              className="rounded-full bg-blue-500 px-3 py-1 text-[10px] text-white shadow-md hover:bg-blue-400"
            >
              ↓ 跳到底部
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
