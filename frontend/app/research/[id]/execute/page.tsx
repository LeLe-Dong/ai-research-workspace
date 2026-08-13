"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Play, RotateCcw, FlaskConical, Loader2, CheckCircle2,
  ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Maximize2, Minimize2,
  History, HelpCircle, Settings2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ResizeSplitter } from "@/components/ui/resize-splitter";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { TaskTree } from "@/features/research/components/task-tree";
import { TimelineStream } from "@/features/research/components/timeline-stream";
import { LiveArtifact } from "@/features/research/components/live-artifact";
import { Console } from "@/features/research/components/console";

import {
  useArtifacts, useReview, useStartResearch, useTasks, useTimeline,
} from "@/features/research/hooks-execute";
import { useResearch } from "@/features/research/hooks";
import { useResearchStream } from "@/features/research/hooks-execute-sse";

const DEFAULT_TASK_WIDTH = 256;
const DEFAULT_TIMELINE_WIDTH = 320;
const DEFAULT_CONSOLE_HEIGHT = 280;

// Preset console heights (in pixels). Used by the S/M/L/全屏 buttons and
// keyboard shortcuts.
const PRESET_HEIGHTS = {
  s: 140,
  m: 280,
  l: 480,
} as const;

export default function ExecutePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const { data: research, isLoading: loadingResearch } = useResearch(id);
  const { data: tasks } = useTasks(id);
  const { data: timeline } = useTimeline(id);
  const { data: artifacts } = useArtifacts(id);
  const { data: review } = useReview(id);

  // Subscribe to SSE for real-time updates (replaces 2s polling)
  useResearchStream(id, !!id);

  const start = useStartResearch(id);
  const [starting, setStarting] = useState(false);

  // Resizable sizes (with localStorage persistence via ResizeSplitter)
  const [taskWidth, setTaskWidth] = useState(DEFAULT_TASK_WIDTH);
  const [timelineWidth, setTimelineWidth] = useState(DEFAULT_TIMELINE_WIDTH);
  const [consoleHeight, setConsoleHeight] = useState(DEFAULT_CONSOLE_HEIGHT);

  // Collapsed states
  const [taskCollapsed, setTaskCollapsed] = useState(false);
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const [consoleCollapsed, setConsoleCollapsed] = useState(false);

  // Fullscreen artifact
  const [artifactFullscreen, setArtifactFullscreen] = useState(false);

  // Selected task for console filtering
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const status = research?.status;

  const onStart = async () => {
    if (starting) return;
    setStarting(true);
    start().catch(() => setStarting(false));
  };

  // Auto-start when the research is pending (e.g. freshly created). The
  // "开始研究" button stays as a fallback, but usually the research begins
  // the moment this page opens, so live logs/progress show immediately.
  // NOTE: must stay above the `if (loadingResearch...) return` guard — hooks
  // cannot appear after a conditional early return.
  useEffect(() => {
    if (status === "pending") {
      setStarting(true);
      start().catch(() => setStarting(false));
    }
    // Intentionally only run once per status change (pending → running).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  // ---- Keyboard shortcuts ----
  // Ctrl/Cmd+J: toggle console
  // Ctrl/Cmd+↑/↓: resize console in 40px steps
  // Esc: clear selected task
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      const tag = (e.target as HTMLElement)?.tagName;
      const inEditable = tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable;

      // Esc: clear task selection (unless in an input)
      if (e.key === "Escape" && !inEditable) {
        if (selectedTaskId) {
          e.preventDefault();
          setSelectedTaskId(null);
        }
        return;
      }

      if (!mod) return;
      const key = e.key.toLowerCase();
      if (key === "j" && !inEditable) {
        e.preventDefault();
        setConsoleCollapsed((v) => !v);
        return;
      }
      if (key === "arrowup" && !inEditable) {
        e.preventDefault();
        if (consoleCollapsed) setConsoleCollapsed(false);
        setConsoleHeight((h) => Math.min(window.innerHeight * 0.7, h + 40));
        return;
      }
      if (key === "arrowdown" && !inEditable) {
        e.preventDefault();
        setConsoleHeight((h) => Math.max(120, h - 40));
        return;
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedTaskId, consoleCollapsed]);

  const setPreset = useCallback((preset: keyof typeof PRESET_HEIGHTS) => {
    setConsoleCollapsed(false);
    setConsoleHeight(PRESET_HEIGHTS[preset]);
  }, []);

  const toggleConsoleFullscreen = useCallback(() => {
    setConsoleCollapsed(false);
    setConsoleHeight(window.innerHeight * 0.7);
  }, []);

  // NOTE: this useMemo must stay ABOVE the `if (loadingResearch || !research)
  // return` guard. React requires a component to call the same hooks in the
  // same order on every render; putting a hook after a conditional early
  // return changes the hook count between the loading and loaded states and
  // triggers React error #310 ("Rendered more hooks than during the previous
  // render").
  const selectedTaskName = useMemo(
    () => tasks?.find((t) => t.id === selectedTaskId)?.name,
    [tasks, selectedTaskId]
  );

  if (loadingResearch || !research) {
    return (
      <div className="container max-w-none px-6 py-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          加载研究中...
        </div>
      </div>
    );
  }

  const isRunning = status === "running";
  const isCompleted = status === "completed";
  const isFailed = status === "failed";

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-background">
      {/* Header bar */}
      <div className="flex items-center justify-between border-b bg-background px-4 py-2 shrink-0">
        <div className="flex items-center gap-3 overflow-hidden">
          <Button variant="ghost" size="icon" asChild className="h-7 w-7 shrink-0">
            <Link href={`/research/${id}`}>
              <ArrowLeft className="h-3.5 w-3.5" />
            </Link>
          </Button>
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted shrink-0">
            <FlaskConical className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-sm font-semibold">{research.title}</h1>
            <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
              <span className="font-mono">{research.id}</span>
              <span>·</span>
              <span>{research.depth}</span>
              <span>·</span>
              <span>{research.priority}</span>
            </div>
          </div>
          <div className="shrink-0">
            {status === "pending" && <Badge variant="secondary" className="h-5">待开始</Badge>}
            {isRunning && (
              <Badge variant="info" className="h-5 gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                执行中
              </Badge>
            )}
            {isCompleted && (
              <Badge variant="success" className="h-5 gap-1">
                <CheckCircle2 className="h-3 w-3" /> 已完成
              </Badge>
            )}
            {isFailed && <Badge variant="destructive" className="h-5">失败</Badge>}
            {(isCompleted || isFailed) && (
              <Badge variant="outline" className="h-5 gap-1 border-warning/50 bg-warning/5 text-warning">
                <History className="h-3 w-3" /> 历史快照（只读）
              </Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {status === "pending" && (
            <Button size="sm" onClick={onStart} disabled={starting}>
              {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              开始研究
            </Button>
          )}
          {(isCompleted || isFailed) && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={onStart}
                disabled={starting}
                title="基于同一目标重新发起一次新执行"
              >
                <RotateCcw className="h-3.5 w-3.5" /> 重新执行
              </Button>
              <Button size="sm" asChild>
                <Link href={`/research/${id}/report`}>查看报告</Link>
              </Button>
            </>
          )}
        </div>
      </div>

      {/* 3-column layout: TaskTree | Timeline | LiveArtifact */}
      {!artifactFullscreen && (
        <div className="flex flex-1 overflow-hidden min-h-0">
          {/* TaskTree panel */}
          <div
            className={cn(
              "shrink-0 border-r flex flex-col min-h-0",
              taskCollapsed ? "w-9" : ""
            )}
            style={!taskCollapsed ? { width: taskWidth } : undefined}
          >
            <div className="flex items-center justify-between border-b bg-muted/30 px-2 py-1.5 shrink-0">
              {!taskCollapsed && <span className="text-xs font-medium">任务进度</span>}
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 ml-auto"
                onClick={() => setTaskCollapsed(!taskCollapsed)}
                title={taskCollapsed ? "展开" : "收起"}
              >
                {taskCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
              </Button>
            </div>
            {!taskCollapsed && (
              <div className="flex-1 overflow-auto">
                <TaskTree
                  tasks={tasks}
                  selectedTaskId={selectedTaskId}
                  onSelectTask={setSelectedTaskId}
                />
              </div>
            )}
          </div>

          {/* Resize handle */}
          {!taskCollapsed && (
            <ResizeSplitter
              direction="horizontal"
              size={taskWidth}
              onResize={setTaskWidth}
              min={180}
              maxPercent={0.4}
              storageKey="task-width"
              ariaLabel="调整任务栏宽度"
            />
          )}

          {/* Timeline panel */}
          <div
            className={cn(
              "shrink-0 border-r flex flex-col min-h-0",
              timelineCollapsed ? "w-9" : ""
            )}
            style={!timelineCollapsed ? { width: timelineWidth } : undefined}
          >
            <div className="flex items-center justify-between border-b bg-muted/30 px-2 py-1.5 shrink-0">
              {!timelineCollapsed && <span className="text-xs font-medium">时间线</span>}
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 ml-auto"
                onClick={() => setTimelineCollapsed(!timelineCollapsed)}
                title={timelineCollapsed ? "展开" : "收起"}
              >
                {timelineCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
              </Button>
            </div>
            {!timelineCollapsed && (
              <div className="flex-1 overflow-hidden">
                <TimelineStream
                  events={timeline}
                  tasks={tasks}
                  onSelectTask={setSelectedTaskId}
                  selectedTaskId={selectedTaskId}
                />
              </div>
            )}
          </div>

          {/* Resize handle */}
          {!timelineCollapsed && (
            <ResizeSplitter
              direction="horizontal"
              size={timelineWidth}
              onResize={setTimelineWidth}
              min={240}
              maxPercent={0.5}
              storageKey="timeline-width"
              ariaLabel="调整时间线宽度"
            />
          )}

          {/* LiveArtifact panel */}
          <div className="flex-1 flex flex-col min-w-0 min-h-0">
            <div className="flex items-center justify-between border-b bg-muted/30 px-2 py-1.5 shrink-0">
              <span className="text-xs font-medium">产物</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5"
                onClick={() => setArtifactFullscreen(true)}
                title="全屏 (Esc 退出)"
              >
                <Maximize2 className="h-3 w-3" />
              </Button>
            </div>
            <div className="flex-1 overflow-auto">
              <LiveArtifact artifacts={artifacts} review={review} />
            </div>
          </div>
        </div>
      )}

      {/* Artifact fullscreen mode (only renders here, hides the rest) */}
      {artifactFullscreen && (
        <div className="flex flex-1 flex-col min-h-0">
          <div className="flex items-center justify-between border-b bg-muted/30 px-2 py-1.5 shrink-0">
            <span className="text-xs font-medium">产物（全屏）</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5"
              onClick={() => setArtifactFullscreen(false)}
              title="退出全屏 (Esc)"
            >
              <Minimize2 className="h-3 w-3" />
            </Button>
          </div>
          <div className="flex-1 overflow-auto">
            <LiveArtifact artifacts={artifacts} review={review} />
          </div>
        </div>
      )}

      {/* Console panel + resize handle on its TOP edge */}
      {!artifactFullscreen && (
        <>
          <ResizeSplitter
            direction="vertical"
            size={consoleHeight}
            onResize={setConsoleHeight}
            min={120}
            maxPercent={0.7}
            storageKey="console-height"
            ariaLabel="调整控制台高度"
          />
          <div
            className={cn(
              "shrink-0 border-t flex flex-col min-h-0",
              consoleCollapsed ? "h-9" : ""
            )}
            style={!consoleCollapsed ? { height: consoleHeight } : undefined}
          >
            <div className="flex items-center justify-between border-b bg-muted/30 px-2 py-1.5 shrink-0">
              <div className="flex items-center gap-2">
                {!consoleCollapsed && <span className="text-xs font-medium">控制台日志</span>}
                {!consoleCollapsed && (
                  <>
                    <span className="hidden sm:flex items-center gap-0.5 text-[10px] text-muted-foreground">
                      {(["s", "m", "l"] as const).map((p) => (
                        <button
                          key={p}
                          type="button"
                          onClick={() => setPreset(p)}
                          title={`设控制台为 ${PRESET_HEIGHTS[p]}px`}
                          className="rounded px-1 hover:bg-accent"
                        >
                          {p.toUpperCase()}
                        </button>
                      ))}
                    </span>
                    {/* Custom pixel size popover */}
                    <Popover>
                      <PopoverTrigger asChild>
                        <button
                          type="button"
                          title="自定义高度（px）"
                          className="flex items-center gap-1 rounded px-1.5 text-[10px] hover:bg-accent"
                        >
                          <Settings2 className="h-2.5 w-2.5" />
                          <span className="tabular-nums text-muted-foreground">
                            {consoleHeight}px
                          </span>
                        </button>
                      </PopoverTrigger>
                      <PopoverContent align="start" className="w-72 p-3">
                        <div className="space-y-2">
                          <p className="text-xs font-medium">自定义控制台高度</p>
                          <p className="text-[10px] text-muted-foreground">
                            输入像素值（120-800）或拖动上方 ⋮⋮ 调整
                          </p>
                          <form
                            onSubmit={(e) => {
                              e.preventDefault();
                              const v = parseInt(
                                (e.currentTarget.elements.namedItem("px") as HTMLInputElement).value,
                                10,
                              );
                              if (!Number.isNaN(v)) setConsoleHeight(v);
                            }}
                            className="flex items-center gap-1.5"
                          >
                            <Input
                              name="px"
                              type="number"
                              min={120}
                              max={800}
                              step={10}
                              defaultValue={consoleHeight}
                              className="h-7 text-xs"
                            />
                            <span className="text-xs text-muted-foreground">px</span>
                            <Button type="submit" size="sm" className="h-7 text-xs">应用</Button>
                          </form>
                          <div className="flex items-center gap-1 pt-1 border-t">
                            <span className="text-[10px] text-muted-foreground">快捷：</span>
                            <button
                              type="button"
                              onClick={() => setPreset("s")}
                              className="rounded px-1.5 py-0.5 text-[10px] hover:bg-accent"
                            >小 ({PRESET_HEIGHTS.s})</button>
                            <button
                              type="button"
                              onClick={() => setPreset("m")}
                              className="rounded px-1.5 py-0.5 text-[10px] hover:bg-accent"
                            >中 ({PRESET_HEIGHTS.m})</button>
                            <button
                              type="button"
                              onClick={() => setPreset("l")}
                              className="rounded px-1.5 py-0.5 text-[10px] hover:bg-accent"
                            >大 ({PRESET_HEIGHTS.l})</button>
                          </div>
                        </div>
                      </PopoverContent>
                    </Popover>
                    <button
                      type="button"
                      onClick={toggleConsoleFullscreen}
                      title="控制台全屏 (Ctrl+J 切换)"
                      className="rounded px-1 hover:bg-accent text-[10px]"
                    >
                      全屏
                    </button>
                  </>
                )}
              </div>
              <div className="flex items-center gap-1 ml-auto">
                <span title="Ctrl+J 切换 / Ctrl+↑↓ 调高度 / Esc 清任务" className="hidden md:inline">
                  <HelpCircle className="h-3 w-3 text-muted-foreground/40" />
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5"
                  onClick={() => setConsoleCollapsed(!consoleCollapsed)}
                  title={consoleCollapsed ? "展开 (Ctrl+J)" : "收起 (Ctrl+J)"}
                >
                  {consoleCollapsed ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </Button>
              </div>
            </div>
            {!consoleCollapsed && (
              <div className="flex-1 overflow-hidden">
                <Console
                  events={timeline}
                  status={status}
                  taskId={selectedTaskId}
                  taskName={selectedTaskName}
                  onClearTask={() => setSelectedTaskId(null)}
                  tasks={tasks}
                />
              </div>
            )}
          </div>
        </>
      )}

      {/* Artifact-fullscreen Esc handler (lives at page level) */}
      <ArtifactFullscreenEsc onEsc={() => setArtifactFullscreen(false)} enabled={artifactFullscreen} />
    </div>
  );
}

/** Tiny subcomponent so the Esc binding stays mounted alongside the page effect. */
function ArtifactFullscreenEsc({
  onEsc,
  enabled,
}: {
  onEsc: () => void;
  enabled: boolean;
}) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onEsc();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onEsc, enabled]);
  return null;
}
