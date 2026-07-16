"use client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime } from "@/lib/utils";
import type { AgentStatus } from "@/lib/types";

export function AgentStatusCard({ agent, loading }: { agent?: AgentStatus; loading?: boolean }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">智能体状态</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        ) : agent ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
              </span>
              <span className="text-sm font-medium">{agent.engine}</span>
              <Badge variant="success" className="ml-auto h-4 px-1.5 text-[10px]">
                Online
              </Badge>
            </div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <dt className="text-muted-foreground">模式</dt>
              <dd className="font-mono">{agent.mode}</dd>
              <dt className="text-muted-foreground">版本</dt>
              <dd className="font-mono">{agent.version}</dd>
              <dt className="text-muted-foreground">最近活跃</dt>
              <dd>{agent.last_active ? formatRelativeTime(agent.last_active) : "—"}</dd>
            </dl>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
