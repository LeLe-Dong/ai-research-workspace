"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Terminal, Loader2, CheckCircle2, AlertTriangle, Info,
  ChevronDown, ChevronRight, Copy, Download, Pause, Play, Filter, X,
  Target, XCircle, Search, ChevronUp, Braces, Eye, EyeOff, RotateCcw,
  BookOpen,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { TimelineEventOut, TaskNode, ResearchStatus } from "@/lib/types";

type LogLevel = "info" | "success" | "warn" | "error" | "log";

function levelIcon(level: LogLevel) {
  if (level === "success") return <CheckCircle2 className="h-3 w-3 text-emerald-500" />;
  if (level === "error") return <AlertTriangle className="h-3 w-3 text-destructive" />;
  if (level === "warn") return <AlertTriangle className="h-3 w-3 text-amber-500" />;
  if (level === "log") return <Terminal className="h-3 w-3 text-cyan-400" />;
  return <Info className="h-3 w-3 text-blue-400" />;
}

function levelClass(level: LogLevel) {
  if (level === "success") return "text-emerald-400";
  if (level === "error") return "text-destructive";
  if (level === "warn") return "text-amber-400";
  if (level === "log") return "text-cyan-400";
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

/** Offset from the very first visible event, in seconds with 1 decimal. */
function fmtRel(ts: string, baselineMs: number): string {
  if (!baselineMs) return "+0.0s";
  const diff = (new Date(ts).getTime() - baselineMs) / 1000;
  return (diff >= 0 ? "+" : "") + diff.toFixed(1) + "s";
}

const LEVEL_LABELS: Record<LogLevel, string> = {
  info: "INFO",
  success: "OK",
  warn: "WARN",
  error: "ERR",
  log: "LOG",
};

// Map TaskNode.phase → Tailwind classes for the small task chip.
const PHASE_COLORS: Record<string, string> = {
  requirement: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  research: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  comparison: "bg-purple-500/15 text-purple-300 border-purple-500/30",
  evaluation: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  report: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  validation: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
};

// Color-code the inner detail border per agent-event phase, so reasoning /
// tool / stderr / session content / etc. are visually distinct.
const DETAIL_BORDER: Record<string, string> = {
  reasoning: "border-purple-500/60",
  tool: "border-cyan-500/60",
  stderr: "border-amber-500/60",
  meta: "border-zinc-500/60",
  log: "border-blue-500/50",
  summarize: "border-emerald-500/60",
  search: "border-indigo-500/60",
  read: "border-indigo-500/60",
  understand: "border-purple-500/60",
  decompose: "border-purple-500/60",
  analyze: "border-amber-500/60",
  derive: "border-pink-500/60",
  review: "border-emerald-500/60",
  validate: "border-cyan-500/60",
};

// Detect "session content" / "Hermes 会话内容" style events — these have
// the full raw output and should be rendered prominently.
function isSessionContentEvent(e: TimelineEventOut): boolean {
  if (e.title.includes("会话内容") || e.title.includes("session content")) return true;
  if (e.detail.startsWith("## Hermes") || e.detail.startsWith("## Session")) return true;
  return false;
}

/** Detect if a string looks like JSON (top-level object or array). */
function isJsonString(s: string): boolean {
  if (!s) return false;
  const t = s.trim();
  if (!t) return false;
  if (t[0] !== "{" && t[0] !== "[") return false;
  try {
    const parsed = JSON.parse(t);
    return typeof parsed === "object" && parsed !== null;
  } catch {
    return false;
  }
}

/** Tiny JSON syntax highlighter. Returns React nodes with colored spans. */
function renderJson(json: string): React.ReactNode {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return <>{json}</>;
  }
  const lines = JSON.stringify(parsed, null, 2).split("\n");
  return lines.map((line, i) => {
    // Match: "key": value patterns and primitives
    const parts: React.ReactNode[] = [];
    let last = 0;
    const tokenRe = /("(?:[^"\\]|\\.)*")(\s*:)?|(\b(?:true|false|null)\b)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
    let m: RegExpExecArray | null;
    let key = 0;
    while ((m = tokenRe.exec(line)) !== null) {
      if (m.index > last) parts.push(line.slice(last, m.index));
      if (m[1]) {
        const isKey = !!m[2];
        parts.push(
          <span key={key++} className={isKey ? "text-cyan-300" : "text-emerald-300"}>
            {m[1]}
          </span>
        );
        if (m[2]) parts.push(<span key={key++} className="text-zinc-500">{m[2]}</span>);
      } else if (m[3]) {
        parts.push(<span key={key++} className="text-amber-300">{m[3]}</span>);
      } else if (m[4]) {
        parts.push(<span key={key++} className="text-purple-300">{m[4]}</span>);
      }
      last = m.index + m[0].length;
    }
    if (last < line.length) parts.push(line.slice(last));
    return (
      <span key={i}>
        {parts}
        {i < lines.length - 1 ? "\n" : ""}
      </span>
    );
  });
}

/** Build a flat searchable haystack per event. */
function haystack(e: TimelineEventOut): string {
  return `${e.phase}\n${e.level}\n${e.title}\n${e.detail}`.toLowerCase();
}

/** Highlight matches inside a string with React nodes. */
function highlightMatches(text: string, query: string, keyBase: number): React.ReactNode {
  if (!query) return text;
  const q = query.toLowerCase();
  const lower = text.toLowerCase();
  const out: React.ReactNode[] = [];
  let last = 0;
  let idx = lower.indexOf(q);
  let k = keyBase;
  while (idx >= 0) {
    if (idx > last) out.push(text.slice(last, idx));
    out.push(
      <mark key={k++} className="bg-yellow-400/40 text-yellow-100 rounded px-0.5">
        {text.slice(idx, idx + q.length)}
      </mark>
    );
    last = idx + q.length;
    idx = lower.indexOf(q, last);
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Console({
  events,
  status,
  taskId,
  taskName,
  onClearTask,
  tasks,
}: {
  events?: TimelineEventOut[];
  status?: ResearchStatus;
  /** When set, only events with matching `task_id` are shown. */
  taskId?: string | null;
  /** Display name of the selected task, shown in the filter chip. */
  taskName?: string;
  /** Handler for the chip's clear button (typically sets taskId=null). */
  onClearTask?: () => void;
  /** All tasks for the research; used to render a small phase chip per line. */
  tasks?: TaskNode[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const [filterLevels, setFilterLevels] = useState<Set<LogLevel>>(
    new Set(["info", "success", "warn", "error", "log"])
  );
  const [filterPhase, setFilterPhase] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [search, setSearch] = useState("");
  const [showRelTime, setShowRelTime] = useState(true);
  const [jsonCollapsed, setJsonCollapsed] = useState(false);

  // Task id → name lookup (for chip rendering)
  const taskNameById = useMemo(() => {
    const m: Record<string, TaskNode> = {};
    (tasks ?? []).forEach((t) => { m[t.id] = t; });
    return m;
  }, [tasks]);

  // Apply task filter first (so phase filter and counts work on the task subset)
  const taskFilteredEvents = useMemo(() => {
    if (!events) return [];
    if (!taskId) return events;
    return events.filter((e) => e.task_id === taskId);
  }, [events, taskId]);

  // Then apply level + phase + search filters
  const filteredEvents = useMemo(() => {
    const q = search.trim().toLowerCase();
    return taskFilteredEvents.filter((e) => {
      const level = (["info", "success", "warn", "error", "log"].includes(e.level) ? e.level : "info") as LogLevel;
      if (!filterLevels.has(level)) return false;
      if (filterPhase && !e.phase.includes(filterPhase)) return false;
      if (q && !haystack(e).includes(q)) return false;
      return true;
    });
  }, [taskFilteredEvents, filterLevels, filterPhase, search]);

  // Baseline timestamp (for relative time column). Use the first visible event
  // in the current task scope; falls back to the first raw event.
  const baselineMs = useMemo(() => {
    const arr = taskFilteredEvents.length > 0 ? taskFilteredEvents : (events ?? []);
    return arr.length > 0 ? new Date(arr[0].ts).getTime() : 0;
  }, [taskFilteredEvents, events]);

  // Auto-scroll to bottom when new events arrive (if enabled)
  useEffect(() => {
    if (!autoScroll) return;
    const el = containerRef.current;
    if (!el) return;
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
      if (distanceFromBottom > 50 && autoScroll) setAutoScroll(false);
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, [autoScroll]);

  // Ctrl/Cmd+F focuses the search input
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "f") {
        e.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
      if (e.key === "Escape" && document.activeElement === searchInputRef.current) {
        if (search) {
          setSearch("");
          searchInputRef.current?.blur();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [search]);

  const isRunning = status === "running";
  const totalEvents = events?.length ?? 0;
  const taskEventCount = taskFilteredEvents.length;
  const visibleCount = filteredEvents.length;
  const errCount = taskFilteredEvents.filter((e) => e.level === "error").length;
  const warnCount = taskFilteredEvents.filter((e) => e.level === "warn").length;
  const elapsed = taskFilteredEvents.length > 0
    ? Math.round((new Date(taskFilteredEvents[taskFilteredEvents.length - 1].ts).getTime() - new Date(taskFilteredEvents[0].ts).getTime()) / 100) / 10
    : 0;

  const tokenEstimate = Math.round(filteredEvents.reduce((acc, e) => acc + (e.title?.length ?? 0) + (e.detail?.length ?? 0), 0) / 4);

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleLevel = (level: LogLevel) => {
    setFilterLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level); else next.add(level);
      return next;
    });
  };

  const formatLine = useCallback((e: TimelineEventOut): string => {
    return `[${fmt(e.ts)}] [${e.phase.padEnd(10)}] ${(LEVEL_LABELS[(e.level as LogLevel)] ?? "INFO").padEnd(4)} ${e.title}${e.detail ? "\n    " + e.detail : ""}`;
  }, []);

  const exportLogs = () => {
    const lines = filteredEvents.map(formatLine);
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `research-log-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyAll = async () => {
    const lines = filteredEvents.map(formatLine);
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  // Unique phases for filter (only within the task-filtered set)
  const phases = useMemo(() => {
    return Array.from(new Set(taskFilteredEvents.map((e) => e.phase)));
  }, [taskFilteredEvents]);

  // Match positions for the search counter
  const matchIndices = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [] as number[];
    const out: number[] = [];
    filteredEvents.forEach((e, i) => {
      if (haystack(e).includes(q)) out.push(i);
    });
    return out;
  }, [search, filteredEvents]);

  // Track current match index. When user uses Enter/Shift+Enter to navigate
  // matches, we record the latest index. Otherwise -1 = no manual jump.
  const [jumpMatchIdx, setJumpMatchIdx] = useState(-1);
  const currentMatchIdx = jumpMatchIdx;

  const jumpToMatch = useCallback((dir: 1 | -1) => {
    if (matchIndices.length === 0) return;
    const cur = currentMatchIdx;
    let next: number;
    if (cur < 0) {
      next = dir === 1 ? matchIndices[0] : matchIndices[matchIndices.length - 1];
    } else {
      const pos = matchIndices.indexOf(cur);
      const nextPos = (pos + dir + matchIndices.length) % matchIndices.length;
      next = matchIndices[nextPos];
    }
    setJumpMatchIdx(next);
    const el = rowRefs.current[filteredEvents[next]?.id];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [matchIndices, currentMatchIdx, filteredEvents]);

  return (
    <div className="flex h-full flex-col bg-zinc-950 font-mono text-sm">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 bg-zinc-900 px-3 py-1.5">
        <div className="flex shrink-0 items-center gap-2">
          <Terminal className="h-3.5 w-3.5 text-zinc-500" />
          <span className="text-sm font-medium text-zinc-300">控制台</span>
          {taskId && (
            <span className="flex items-center gap-1 rounded-full border border-cyan-500/40 bg-cyan-500/10 px-2 py-0.5 text-xs text-cyan-300">
              <Target className="h-3 w-3" />
              <span className="max-w-[160px] truncate font-medium">{taskName || "任务"}</span>
              <span className="text-cyan-400/70 tabular-nums">{taskEventCount}</span>
              {onClearTask && (
                <button
                  type="button"
                  onClick={onClearTask}
                  className="ml-0.5 hover:text-cyan-100"
                  title="清除任务过滤 (Esc)"
                >
                  <XCircle className="h-3 w-3" />
                </button>
              )}
            </span>
          )}
          {isRunning && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />}
        </div>

        <div className="flex shrink-0 items-center gap-2 text-xs text-zinc-500">
          <span>事件：<span className="text-zinc-300 tabular-nums">{visibleCount}</span>/<span className="tabular-nums">{taskId ? taskEventCount : totalEvents}</span></span>
          {warnCount > 0 && <span className="text-amber-400">W:<span className="tabular-nums">{warnCount}</span></span>}
          {errCount > 0 && <span className="text-destructive">E:<span className="tabular-nums">{errCount}</span></span>}
          <span className="tabular-nums">{elapsed.toFixed(1)}s</span>
          <span className="text-zinc-600 tabular-nums">~{tokenEstimate} tok</span>
        </div>
      </div>

      {/* Search bar */}
      <div className="flex items-center gap-1.5 border-b border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs">
        <Search className="h-3.5 w-3.5 text-zinc-500" />
        <input
          ref={searchInputRef}
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              jumpToMatch(e.shiftKey ? -1 : 1);
            }
          }}
          placeholder="搜索日志 (Ctrl+F)"
          className="flex-1 bg-transparent px-1 py-0.5 text-sm text-zinc-200 outline-none placeholder:text-zinc-600"
        />
        {search && (
          <span className="shrink-0 text-xs text-zinc-500 tabular-nums">
            {currentMatchIdx >= 0 ? matchIndices.indexOf(currentMatchIdx) + 1 : "0"}/{matchIndices.length}
          </span>
        )}
        {search && (
          <button
            type="button"
            onClick={() => { setSearch(""); searchInputRef.current?.blur(); }}
            className="rounded p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
            title="清空 (Esc)"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          onClick={() => jumpToMatch(-1)}
          disabled={matchIndices.length === 0}
          className="rounded p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30"
          title="上一匹配 (Shift+Enter)"
        >
          <ChevronUp className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => jumpToMatch(1)}
          disabled={matchIndices.length === 0}
          className="rounded p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30"
          title="下一匹配 (Enter)"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
        <span className="mx-1 text-zinc-700">|</span>
        <button
          type="button"
          onClick={() => setShowRelTime((v) => !v)}
          className={cn(
            "rounded px-1.5 py-0.5 text-xs",
            showRelTime ? "bg-zinc-800 text-cyan-300" : "text-zinc-600 hover:text-zinc-400"
          )}
          title="切换相对时间列"
        >
          +T
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-1.5 border-b border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs">
        <Filter className="h-3.5 w-3.5 text-zinc-500" />
        {(["info", "success", "warn", "error", "log"] as LogLevel[]).map((lvl) => (
          <button
            key={lvl}
            type="button"
            onClick={() => toggleLevel(lvl)}
            className={cn(
              "px-2 py-0.5 rounded text-xs font-medium transition-colors",
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
              className="bg-zinc-900 px-1.5 py-0.5 text-xs text-zinc-400 outline-none rounded"
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
            className="h-6 px-2 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            title="复制可见日志"
          >
            {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
            <span className="ml-1">{copied ? "已复制" : "复制"}</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={exportLogs}
            className="h-6 px-2 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            title="导出日志为 .txt"
          >
            <Download className="h-3.5 w-3.5" />
            <span className="ml-1">.txt</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setAutoScroll(!autoScroll)}
            className="h-6 px-2 text-xs hover:bg-zinc-800"
            title={autoScroll ? "暂停自动滚动" : "恢复自动滚动"}
            disabled={!isRunning}
          >
            {autoScroll ? (
              <><Pause className="h-3.5 w-3.5 text-emerald-500" /><span className="ml-1 text-emerald-500">跟随</span></>
            ) : (
              <><Play className="h-3.5 w-3.5 text-zinc-400" /><span className="ml-1 text-zinc-400">已暂停</span></>
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
          <div className="px-3 py-2 space-y-1">
            {filteredEvents.map((e, idx) => {
              const level = (["info", "success", "warn", "error", "log"].includes(e.level) ? e.level : "info") as LogLevel;
              const hasDetail = !!e.detail && e.detail.length > 0;
              // Auto-expand details while running (or when a task filter is
              // active) so the user sees the full live trace (benchmark logs,
              // reasoning, tool calls) without clicking each row; collapses
              // once the research completes.
              const isOpen = (taskId || isRunning) ? hasDetail : expanded.has(e.id);
              const isHighlight = currentMatchIdx >= 0 && filteredEvents[currentMatchIdx]?.id === e.id;
              const task = e.task_id ? taskNameById[e.task_id] : null;
              const isJson = hasDetail && isJsonString(e.detail);
              const isZebra = idx % 2 === 1;
              return (
                <div
                  key={e.id}
                  ref={(el) => { rowRefs.current[e.id] = el; }}
                  className={cn(
                    "group rounded",
                    isZebra && "bg-zinc-900/30",
                    isHighlight && "ring-1 ring-yellow-400/80 bg-yellow-500/10"
                  )}
                >
                  <button
                    type="button"
                    onClick={() => hasDetail && toggleExpanded(e.id)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded px-2 py-1 text-left leading-relaxed hover:bg-zinc-800/70 transition-colors",
                      hasDetail && "cursor-pointer"
                    )}
                  >
                    <span className="shrink-0 text-xs text-zinc-500 tabular-nums">{fmt(e.ts)}</span>
                    {showRelTime && (
                      <span className="shrink-0 w-14 text-xs text-cyan-400/80 tabular-nums">{fmtRel(e.ts, baselineMs)}</span>
                    )}
                    <span className="shrink-0 w-24 truncate text-xs text-zinc-500">[{e.phase}]</span>
                    <span className={cn("shrink-0 w-14 flex items-center gap-1 text-xs font-semibold", levelClass(level))}>
                      {levelIcon(level)}
                      {LEVEL_LABELS[level]}
                    </span>
                    {task && (
                      <span className={cn(
                        "shrink-0 max-w-[140px] truncate rounded border px-1.5 py-0 text-[11px] font-medium",
                        PHASE_COLORS[task.phase] || "border-zinc-700 bg-zinc-800 text-zinc-400"
                      )} title={task.name}>
                        {task.name}
                      </span>
                    )}
                    <span className="flex-1 truncate text-sm text-zinc-200">
                      {search ? highlightMatches(e.title, search, 0) : e.title}
                    </span>
                    {hasDetail && (
                      <span className="shrink-0 flex items-center gap-1 text-zinc-500">
                        {isJson && <Braces className="h-3 w-3 text-cyan-500" />}
                        {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      </span>
                    )}
                  </button>
                  {hasDetail && isOpen && (
                    <div className={cn(
                      "ml-6 mr-2 mt-1 mb-2 rounded border-l-2 bg-zinc-900/80 px-3 py-2 text-zinc-300",
                      DETAIL_BORDER[e.phase] || "border-blue-500/50",
                      isSessionContentEvent(e) && "border-emerald-500/70 bg-emerald-950/30"
                    )}>
                      {isJson ? (
                        <JsonDetail json={e.detail} collapsed={jsonCollapsed} onToggleCollapse={() => setJsonCollapsed((v) => !v)} search={search} />
                      ) : isSessionContentEvent(e) ? (
                        <SessionContentBlock detail={e.detail} search={search} />
                      ) : (
                        <pre className="whitespace-pre-wrap break-all font-mono text-[13px] leading-6 text-zinc-300">
                          {search ? highlightMatches(e.detail, search, 100000) : e.detail}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="px-4 py-6 text-sm text-zinc-600">// {search ? "无匹配" : "等待智能体..."}</p>
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
              className="rounded-full bg-blue-500 px-3 py-1 text-xs text-white shadow-md hover:bg-blue-400"
            >
              ↓ 跳到底部
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** JSON detail renderer with collapse/expand + search highlighting. */
function JsonDetail({
  json,
  collapsed,
  onToggleCollapse,
  search,
}: {
  json: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
  search: string;
}) {
  // Pretty-print with optional collapse to top-level keys only
  let pretty: string;
  let summary: string;
  try {
    const parsed = JSON.parse(json);
    pretty = JSON.stringify(parsed, null, 2);
    summary = Array.isArray(parsed)
      ? `Array(${parsed.length})`
      : `Object {${Object.keys(parsed).length} keys}`;
  } catch {
    pretty = json;
    summary = "(invalid JSON)";
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-xs">
        <Braces className="h-3.5 w-3.5 text-cyan-500" />
        <span className="text-cyan-300 font-medium">{summary}</span>
        <button
          type="button"
          onClick={onToggleCollapse}
          className="ml-auto inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
          title={collapsed ? "展开 JSON" : "折叠 JSON"}
        >
          {collapsed ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
          {collapsed ? "展开" : "折叠"}
        </button>
      </div>
      <pre className="whitespace-pre-wrap break-all font-mono text-[13px] leading-6 text-zinc-200">
        {collapsed
          ? (search ? highlightMatches(pretty.split("\n").slice(0, 1).join("\n"), search, 200000) : pretty.split("\n").slice(0, 1).join("\n"))
          : (search ? highlightMatches(pretty, search, 200000) : renderJson(pretty))}
      </pre>
    </div>
  );
}

/**
 * Renders the full "session content" payload (Hermes raw output, etc.)
 * with a header strip showing metadata + a Copy button. The body is shown
 * in a scrollable, monospace block.
 */
function SessionContentBlock({ detail, search }: { detail: string; search: string }) {
  const [copied, setCopied] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  // Parse the structured header we emit from the agent:
  //   "## Hermes 完整会话输出 (1234 chars)\n\nprofile: ... | skills: ...\n
  //    raw_output: 5678 chars\ncleaned: 1234 chars\n\n---\n\n<body>"
  let header: React.ReactNode = null;
  let body = detail;
  const m = detail.match(/^(## [^\n]+\n\n[^\n]+\n[^\n]+\n[^\n]+\n\n---\n\n)/);
  if (m) {
    const headerText = m[1];
    body = detail.slice(m[0].length);
    header = (
      <pre className="whitespace-pre-wrap font-mono text-xs leading-5 text-emerald-200/80">
        {search ? highlightMatches(headerText, search, 300000) : headerText}
      </pre>
    );
  }

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(detail);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-2">
      {header}
      <div className="flex items-center gap-2 text-xs">
        <BookOpen className="h-3.5 w-3.5 text-emerald-400" />
        <span className="text-emerald-300 font-medium">完整会话输出</span>
        <span className="text-zinc-500">·</span>
        <span className="text-zinc-400 tabular-nums">{body.length.toLocaleString()} 字符</span>
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          className="ml-2 rounded px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
        >
          {collapsed ? "展开" : "折叠"}
        </button>
        <button
          type="button"
          onClick={onCopy}
          className="ml-auto inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
          title="复制完整会话内容"
        >
          {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "已复制" : "复制全部"}
        </button>
      </div>
      {!collapsed && (
        <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap break-all rounded border border-emerald-500/20 bg-zinc-950/60 p-3 font-mono text-[13px] leading-6 text-zinc-200">
          {search ? highlightMatches(body, search, 400000) : body}
        </pre>
      )}
    </div>
  );
}
