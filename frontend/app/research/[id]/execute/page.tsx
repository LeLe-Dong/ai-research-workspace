"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Play, RotateCcw, FlaskConical, Loader2, CheckCircle2,
  ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Maximize2, Minimize2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ResizeSplitter } from "@/components/ui/resize-splitter";
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

  const status = research?.status;

  const onStart = async () => {
    setStarting(true);
    try {
      await start();
    } finally {
      setStarting(false);
    }
  };

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
            {isCompleted && <Badge variant="success" className="h-5 gap-1"><CheckCircle2 className="h-3 w-3" /> 已完成</Badge>}
            {isFailed && <Badge variant="destructive" className="h-5">失败</Badge>}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {status === "pending" && (
            <Button size="sm" onClick={onStart} disabled={starting}>
              {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              开始研究
            </Button>
          )}
          {isCompleted && (
            <>
              <Button size="sm" variant="outline" onClick={onStart} disabled={starting}>
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
              <TaskTree tasks={tasks} />
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
              <TimelineStream events={timeline} />
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
              onClick={() => setArtifactFullscreen(!artifactFullscreen)}
              title={artifactFullscreen ? "退出全屏" : "全屏"}
            >
              {artifactFullscreen ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
            </Button>
          </div>
          <div className="flex-1 overflow-auto">
            <LiveArtifact artifacts={artifacts} review={review} />
          </div>
        </div>
      </div>

      {/* Console panel (bottom) */}
      <div
        className={cn(
          "shrink-0 border-t flex flex-col min-h-0",
          consoleCollapsed ? "h-9" : ""
        )}
        style={!consoleCollapsed ? { height: consoleHeight } : undefined}
      >
        <div className="flex items-center justify-between border-b bg-muted/30 px-2 py-1.5 shrink-0">
          {!consoleCollapsed && <span className="text-xs font-medium">控制台日志</span>}
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5 ml-auto"
            onClick={() => setConsoleCollapsed(!consoleCollapsed)}
            title={consoleCollapsed ? "展开" : "收起"}
          >
            {consoleCollapsed ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </Button>
        </div>
        {!consoleCollapsed && (
          <div className="flex-1 overflow-hidden">
            <Console events={timeline} status={status} />
          </div>
        )}
      </div>

      {/* Resize handle for console (always visible when not collapsed) */}
      {!consoleCollapsed && (
        <ResizeSplitter
          direction="vertical"
          size={consoleHeight}
          onResize={setConsoleHeight}
          min={120}
          maxPercent={0.7}
          storageKey="console-height"
          ariaLabel="调整控制台高度"
        />
      )}
    </div>
  );
}
