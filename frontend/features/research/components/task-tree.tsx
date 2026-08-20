"use client";
import { CheckCircle2, Circle, Loader2, FlaskConical, X } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { TaskNode } from "@/lib/types";

const PHASE_META: Record<string, { label: string; color: string; icon?: string }> = {
  requirement: { label: "需求分析", color: "bg-blue-500" },
  research: { label: "信息收集", color: "bg-indigo-500" },
  comparison: { label: "对比分析", color: "bg-purple-500" },
  evaluation: { label: "可行性评估", color: "bg-amber-500" },
  report: { label: "报告撰写", color: "bg-emerald-500" },
  validation: { label: "环境验证 (K8s)", color: "bg-cyan-500", icon: "☸" },
};

function StatusIcon({ status }: { status: string }) {
  if (status === "done") return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
  return <Circle className="h-4 w-4 text-muted-foreground/40" />;
}

interface TaskTreeProps {
  tasks?: TaskNode[];
  /** Currently selected task id; click again or the × chip to clear. */
  selectedTaskId?: string | null;
  /** Called when the user picks a task. Pass null to clear. */
  onSelectTask?: (taskId: string | null) => void;
}

export function TaskTree({ tasks, selectedTaskId, onSelectTask }: TaskTreeProps) {
  if (!tasks) return <div className="p-4 text-xs text-muted-foreground">加载任务中...</div>;
  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 p-8 text-center">
        <FlaskConical className="h-8 w-8 text-muted-foreground/40" />
        <p className="text-xs text-muted-foreground">暂无任务。开始研究后自动生成计划。</p>
      </div>
    );
  }

  // Group by phase
  const byPhase: Record<string, TaskNode[]> = {};
  for (const t of tasks) {
    if (!byPhase[t.phase]) byPhase[t.phase] = [];
    byPhase[t.phase].push(t);
  }

  const overallProgress = Math.round(
    tasks.reduce((sum, t) => sum + t.progress, 0) / tasks.length,
  );

  const selectedTask = selectedTaskId ? tasks.find(t => t.id === selectedTaskId) : null;

  const handleClick = (id: string) => {
    if (!onSelectTask) return;
    onSelectTask(selectedTaskId === id ? null : id);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            TaskTree
          </p>
          <Badge variant="outline" className="h-4 px-1 text-[10px]">
            {tasks.filter((t) => t.status === "done").length}/{tasks.length}
          </Badge>
        </div>
        <Progress value={overallProgress} className="mt-2 h-1" />
        <p className="mt-1 text-[10px] text-muted-foreground">{overallProgress}% 总进度</p>
        {selectedTask && (
          <div className="mt-2 flex items-center gap-1.5 rounded-md border bg-primary/5 px-2 py-1 text-[10px]">
            <span className="text-primary font-medium">筛选中</span>
            <span className="flex-1 truncate text-muted-foreground">{selectedTask.name}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-4 w-4 shrink-0 hover:bg-primary/10"
              onClick={() => onSelectTask?.(null)}
              title="清除选择 (Esc)"
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-4 p-3">
          {Object.entries(byPhase).map(([phase, items]) => {
            const meta = PHASE_META[phase] || { label: phase, color: "bg-gray-500" };
            return (
              <div key={phase}>
                <div className="mb-1.5 flex items-center gap-2 px-1">
                  <span className={`h-1.5 w-1.5 rounded-full ${meta.color}`} />
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {meta.label}
                  </p>
                </div>
                <ul className="space-y-0.5">
                  {items.map((t) => {
                    const isK8s = t.phase === "validation";
                    const isSelected = selectedTaskId === t.id;
                    return (
                      <li key={t.id}>
                        <button
                          type="button"
                          onClick={() => handleClick(t.id)}
                          className={cn(
                            "group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors cursor-pointer",
                            "hover:bg-accent/40",
                            isK8s && t.status === "running" && "bg-cyan-500/10 ring-1 ring-cyan-500/30 animate-pulse",
                            isSelected && "bg-primary/10 ring-1 ring-primary/40 hover:bg-primary/15"
                          )}
                          title={isSelected ? "点击取消选择" : `点击查看「${t.name}」的日志`}
                          aria-pressed={isSelected}
                        >
                          <StatusIcon status={t.status} />
                          <span className={cn(
                            "flex-1 truncate text-xs",
                            isSelected && "font-medium text-foreground"
                          )}>
                            {isK8s && <span className="mr-1">☸</span>}
                            {t.name}
                          </span>
                          {isK8s && t.status === "done" && (
                            <span className="text-[10px] text-cyan-600">✓ 集群已验证</span>
                          )}
                          {t.progress > 0 && t.progress < 100 && (
                            <span className="text-[10px] text-muted-foreground">{t.progress}%</span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
