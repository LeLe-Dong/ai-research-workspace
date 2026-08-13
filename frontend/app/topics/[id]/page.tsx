"use client";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { useTopic, useIterateTopic } from "@/features/topics/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  GitBranch, ArrowRight, ArrowUpRight, Play, History, Loader2, Target, MessageSquare,
} from "lucide-react";

const statusLabel: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
};

export default function TopicDetailPage() {
  const params = useParams();
  const router = useRouter();
  const topicId = params.id as string;
  const { data, isLoading } = useTopic(topicId);
  const iterate = useIterateTopic();

  const [nextGoal, setNextGoal] = useState("");
  const [nextConstraints, setNextConstraints] = useState("");
  const [nextOutput, setNextOutput] = useState("");
  const [commitMsg, setCommitMsg] = useState("");
  const [iterOpen, setIterOpen] = useState(false);

  const latest = data?.sessions?.[data.sessions.length - 1];

  const handleIterate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!latest) return;
    try {
      await iterate.mutateAsync({
        topicId,
        goal: nextGoal || undefined,
        constraints: nextConstraints || undefined,
        expected_output: nextOutput || undefined,
        commit_message: commitMsg,
      });
      setIterOpen(false);
      router.refresh();
    } catch {
      /* toast in hook */
    }
  };

  if (isLoading) {
    return <div className="container px-6 py-6 text-sm text-muted-foreground">加载中...</div>;
  }
  if (!data) {
    return <div className="container px-6 py-6 text-sm text-muted-foreground">主题不存在</div>;
  }

  const sessions = data.sessions || [];

  return (
    <div className="container max-w-none px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-blue-500" />
            <h1 className="text-2xl font-semibold">{data.name}</h1>
            <Badge variant="outline" className="text-xs">{sessions.length} 轮迭代</Badge>
          </div>
          {data.description && <p className="mt-1 text-sm text-muted-foreground">{data.description}</p>}
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/topics">
            <ArrowUpRight className="mr-1.5 h-3.5 w-3.5" />
            返回主题列表
          </Link>
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* Iteration timeline */}
        <div className="relative space-y-4">
          {sessions.length === 0 && (
            <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">尚无研究轮次</CardContent></Card>
          )}
          {sessions.map((s, idx) => (
            <div key={s.id} className="relative flex gap-4">
              {idx < sessions.length - 1 && (
                <div className="absolute left-[11px] top-6 h-full w-px bg-border" />
              )}
              <div className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full border-2 bg-background"
                   style={{ borderColor: s.status === "completed" ? "#10b981" : "#6366f1" }}>
                <span className="flex h-full w-full items-center justify-center text-[9px] font-bold">{s.iteration}</span>
              </div>
              <Card className="flex-1 p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">第 {s.iteration} 轮</span>
                      <Badge variant={s.status === "completed" ? "success" : "secondary"}>
                        {statusLabel[s.status] || s.status}
                      </Badge>
                      {idx === sessions.length - 1 && (
                        <Badge variant="info" className="text-xs">最新</Badge>
                      )}
                    </div>
                    <p className="text-sm">{s.title}</p>
                    <p className="text-xs text-muted-foreground line-clamp-2">目标：{s.goal}</p>
                    {s.constraints && (
                      <p className="text-xs text-muted-foreground/80 line-clamp-1">约束：{s.constraints}</p>
                    )}
                    <p className="text-xs text-muted-foreground">{new Date(s.created_at).toLocaleString()}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button asChild variant="ghost" size="sm">
                      <Link href={`/research/${s.id}`}>
                        <ArrowUpRight className="mr-1 h-3.5 w-3.5" />
                        打开
                      </Link>
                    </Button>
                  </div>
                </div>
              </Card>
            </div>
          ))}

          {/* Next iteration form */}
          {latest && (
            <div className="ml-10">
              <Button variant="outline" size="sm" onClick={() => setIterOpen(!iterOpen)} className="mb-3">
                <Play className="mr-1.5 h-3.5 w-3.5 text-emerald-500" />
                {iterOpen ? "收起" : "发起下一轮迭代"}
              </Button>
              {iterOpen && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Target className="h-4 w-4 text-emerald-500" />
                      第 {sessions.length + 1} 轮 · 调整研究边界
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={handleIterate} className="space-y-3">
                      <p className="text-xs text-muted-foreground">
                        留空则继承上一轮的边界；填写则覆盖。上一轮目标：<span className="text-foreground/70">{latest.goal.slice(0, 60)}...</span>
                      </p>
                      <div className="space-y-1.5">
                        <label className="text-xs text-muted-foreground">本轮研究目标（覆盖）</label>
                        <Textarea value={nextGoal} onChange={(e) => setNextGoal(e.target.value)} rows={3}
                          placeholder={latest.goal} />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs text-muted-foreground">约束条件（覆盖）</label>
                        <Textarea value={nextConstraints} onChange={(e) => setNextConstraints(e.target.value)} rows={2}
                          placeholder={latest.constraints || "（无）"} />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs text-muted-foreground">预期产出（覆盖）</label>
                        <Textarea value={nextOutput} onChange={(e) => setNextOutput(e.target.value)} rows={2}
                          placeholder={latest.expected_output || "（无）"} />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs text-muted-foreground">本次调整说明（commit message）</label>
                        <Input value={commitMsg} onChange={(e) => setCommitMsg(e.target.value)}
                          placeholder="如：第1轮发现哨兵扩展性差，本轮转向 Cluster" />
                      </div>
                      <Button type="submit" disabled={iterate.isPending} className="w-full">
                        {iterate.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                        启动第 {sessions.length + 1} 轮研究
                      </Button>
                    </form>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </div>

        {/* Sidebar */}
        <aside className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <History className="h-4 w-4 text-blue-500" />
                迭代说明
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p>• 每轮研究完成后，查看报告与评分</p>
              <p>• 审核后调整研究边界（目标/约束/产出）</p>
              <p>• 发起下一轮，历史完整保留</p>
              <p>• 各轮独立成研究，可单独打开/重跑</p>
            </CardContent>
          </Card>
          {latest && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">最新一轮</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-xs">
                <div className="flex justify-between"><span className="text-muted-foreground">轮次</span><span>第 {latest.iteration} 轮</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">状态</span>
                  <Badge variant={latest.status === "completed" ? "success" : "secondary"}>{statusLabel[latest.status]}</Badge>
                </div>
                <div className="flex justify-between"><span className="text-muted-foreground">深度</span><span>{latest.depth}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">优先级</span><span>{latest.priority}</span></div>
                <Button asChild variant="outline" size="sm" className="w-full mt-2">
                  <Link href={`/research/${latest.id}`}>
                    <ArrowRight className="mr-1.5 h-3.5 w-3.5" />
                    打开最新研究
                  </Link>
                </Button>
              </CardContent>
            </Card>
          )}
        </aside>
      </div>
    </div>
  );
}
