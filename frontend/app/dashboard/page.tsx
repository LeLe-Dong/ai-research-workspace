"use client";
import { useDashboard } from "@/features/dashboard/hooks";
import { StatsGrid } from "@/features/dashboard/components/stats-grid";
import { RecentResearches } from "@/features/dashboard/components/recent-researches";
import { PopularKnowledge } from "@/features/dashboard/components/popular-knowledge";
import { AgentStatusCard } from "@/features/dashboard/components/agent-status";
import { RunningSection } from "@/features/dashboard/components/running-section";
import { ApiError } from "@/lib/api";

export default function DashboardPage() {
  const { data, isLoading, error } = useDashboard();

  return (
    <div className="container max-w-none px-6 py-6">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">工作台</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Overview of your research workspace, agent status, and recent activity.
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          加载工作台失败
          {error instanceof ApiError ? ` (${error.status})` : `: ${(error as Error).message}`}
          <span className="ml-2 text-xs">— 请确认后端服务运行于端口 8003。</span>
        </div>
      )}

      <div className="space-y-6">
        <RunningSection items={data?.recent} loading={isLoading} />

        <StatsGrid stats={data?.stats} loading={isLoading} />

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <RecentResearches items={data?.recent} loading={isLoading} />
          </div>
          <div className="space-y-6">
            <PopularKnowledge items={data?.popular} loading={isLoading} />
            <AgentStatusCard agent={data?.agent} loading={isLoading} />
          </div>
        </div>
      </div>
    </div>
  );
}
