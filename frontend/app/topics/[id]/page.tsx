"use client";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { useTopic, useIterateTopic, type TopicSession } from "@/features/topics/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  GitBranch, ArrowRight, ArrowUpRight, Play, History, Loader2, Target, MessageSquare, Server, Sparkles, Wand2, CheckCircle2, X,
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

  const [nextTitle, setNextTitle] = useState("");
  const [nextGoal, setNextGoal] = useState("");
  const [nextConstraints, setNextConstraints] = useState("");
  const [nextOutput, setNextOutput] = useState("");
  const [nextK8s, setNextK8s] = useState<number | null>(null);
  const [commitMsg, setCommitMsg] = useState("");
  const [iterOpen, setIterOpen] = useState(false);

  // AI 生成方案 state
  const [aiQuickOpen, setAiQuickOpen] = useState(false);
  const [aiSubject, setAiSubject] = useState("");
  const [aiGenerated, setAiGenerated] = useState<{ plan: any; source: string } | null>(null);
  const [aiGenerating, setAiGenerating] = useState(false);

  const generateAiPlan = async () => {
    const s = aiSubject.trim();
    if (!s) { toast.error("请先输入一句话研究主题"); return; }
    setAiGenerating(true);
    try {
      const { api } = await import("@/lib/api");
      const data = await api.post<any>("/api/v1/researches/generate-plan", { subject: s, use_llm: true });
      setAiGenerated({ plan: data.plan, source: data.source });
      toast.success("已生成研究方案，可预览后填入表单");
    } catch (e) {
      toast.error("生成失败", { description: (e as Error).message });
    } finally {
      setAiGenerating(false);
    }
  };

  const applyAiPlan = () => {
    if (!aiGenerated) return;
    const p = aiGenerated.plan;
    setNextTitle(p.title || "");
    setNextGoal(p.goal || "");
    setNextConstraints(p.constraints || "");
    setNextOutput(p.expected_output || "");
    if (typeof p.requires_k8s_validation === "number") {
      setNextK8s(p.requires_k8s_validation === 1 ? 1 : p.requires_k8s_validation === -1 ? -1 : 0);
    }
    setAiQuickOpen(false);
    setAiGenerated(null);
    toast.success("AI 生成方案已填入表单", { description: "可继续修改后提交" });
  };

  const latest = data?.sessions?.[data.sessions.length - 1];
  const isFirstRound = !latest;

  const handleIterate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await iterate.mutateAsync({
        topicId,
        title: nextTitle || undefined,
        goal: nextGoal || undefined,
        constraints: nextConstraints || undefined,
        expected_output: nextOutput || undefined,
        requires_k8s_validation: nextK8s ?? undefined,
        commit_message: commitMsg,
      });
      setIterOpen(false);
      setNextTitle("");
      setNextGoal("");
      setNextConstraints("");
      setNextOutput("");
      setNextK8s(null);
      setCommitMsg("");
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
        {/* Baseline overview */}
        {sessions.length > 0 && (
          <div className="lg:col-span-2 mb-2">
            <BaselineOverview data={data} sessions={sessions} />
          </div>
        )}

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
                  <div className="flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">第 {s.iteration} 轮</span>
                      <Badge variant={s.status === "completed" ? "success" : "secondary"}>
                        {statusLabel[s.status] || s.status}
                      </Badge>
                      {idx === sessions.length - 1 && (
                        <Badge variant="info" className="text-xs">最新</Badge>
                      )}
                      {s.score != null && (
                        <Badge variant={s.score >= 8 ? "success" : s.score >= 6 ? "warning" : "destructive"}
                          className="h-5 px-2 text-xs">
                          评分 {s.score.toFixed(1)}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm">{s.title}</p>
                    <p className="text-xs text-muted-foreground line-clamp-2">目标：{s.goal}</p>
                    {s.constraints && (
                      <p className="text-xs text-muted-foreground/80 line-clamp-1">约束：{s.constraints}</p>
                    )}
                    {s.k8s_summary && (
                      <p className="text-xs text-cyan-600 dark:text-cyan-300">
                        <Server className="mr-1 inline h-3 w-3" />
                        {s.k8s_summary}
                      </p>
                    )}
                    {s.report_excerpt && (
                      <details className="mt-1 rounded border bg-muted/30 p-2">
                        <summary className="cursor-pointer text-[10px] font-medium text-muted-foreground">
                          报告摘要
                        </summary>
                        <p className="mt-1 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-muted-foreground">
                          {s.report_excerpt.length > 500 ? s.report_excerpt.slice(0, 500) + "…" : s.report_excerpt}
                        </p>
                      </details>
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

          {/* First round OR next iteration form */}
          <div className="ml-10">
            <Button variant="outline" size="sm" onClick={() => setIterOpen(!iterOpen)} className="mb-3">
              <Play className="mr-1.5 h-3.5 w-3.5 text-emerald-500" />
              {iterOpen ? "收起" : isFirstRound ? "开始第 1 轮研究" : "发起下一轮迭代"}
            </Button>
            {iterOpen && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Target className="h-4 w-4 text-emerald-500" />
                    {isFirstRound ? `第 1 轮 · 定义研究边界` : `第 ${sessions.length + 1} 轮 · 调整研究边界`}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleIterate} className="space-y-3">
                    <p className="text-xs text-muted-foreground">
                      {isFirstRound
                        ? "填写本轮研究目标（可留空，将基于主题名自动生成）"
                        : "可基于上一轮结果调整研究规范与目标：留空字段继承上一轮，填写则覆盖。"}
                    </p>
                    {/* AI 生成方案 — 第一轮时可用 */}
                    {isFirstRound && (
                      <div className="rounded border border-dashed border-purple-500/30 bg-purple-500/5 p-3 space-y-2">
                        <div className="flex items-center gap-2">
                          <Wand2 className="h-3.5 w-3.5 text-purple-400" />
                          <span className="text-xs font-medium">AI 一键生成研究方案</span>
                        </div>
                        <p className="text-[10px] text-muted-foreground">输入一句话主题，AI 自动生成完整研究计划</p>
                        {!aiQuickOpen ? (
                          <Button type="button" variant="outline" size="sm" onClick={() => {
                            setAiQuickOpen(true);
                            if (!aiSubject && data?.name) setAiSubject(data.name);
                          }}>
                            <Sparkles className="mr-1.5 h-3.5 w-3.5 text-purple-400" />
                            开始生成
                          </Button>
                        ) : (
                          <div className="space-y-2 mt-2">
                            <div className="flex gap-2">
                              <Input
                                value={aiSubject}
                                onChange={(e) => setAiSubject(e.target.value)}
                                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); generateAiPlan(); } }}
                                placeholder="输入一句话研究主题..."
                              />
                              <Button type="button" size="sm" onClick={generateAiPlan} disabled={aiGenerating}>
                                {aiGenerating ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Sparkles className="mr-1.5 h-3.5 w-3.5" />}
                                生成
                              </Button>
                            </div>
                            {aiGenerated && (
                              <div className="rounded-md border bg-background/60 p-3 space-y-2">
                                <p className="text-[10px] font-medium text-emerald-600 flex items-center gap-1">
                                  <CheckCircle2 className="h-3.5 w-3.5" />
                                  已生成方案（来源：{aiGenerated.source}）
                                </p>
                                <p className="text-sm font-medium">{aiGenerated.plan.title}</p>
                                <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{aiGenerated.plan.goal}</p>
                                <div className="flex flex-wrap gap-1.5 text-[10px]">
                                  <Badge variant="outline">{aiGenerated.plan.depth}</Badge>
                                  <Badge variant="outline">优先级 {aiGenerated.plan.priority}</Badge>
                                  <Badge variant="outline">k8s验证: {aiGenerated.plan.requires_k8s_validation === 1 ? "开" : "自动"}</Badge>
                                </div>
                                <div className="mt-2 flex gap-2">
                                  <Button type="button" size="sm" onClick={applyAiPlan}>
                                    <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                                    填入表单
                                  </Button>
                                  <Button type="button" variant="ghost" size="sm" onClick={() => setAiGenerated(null)}>
                                    <X className="mr-1.5 h-3.5 w-3.5" />
                                    丢弃
                                  </Button>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                    {latest && (
                      <div className="rounded border bg-muted/30 p-2.5 text-[11px] leading-relaxed text-muted-foreground">
                        <p className="flex items-center gap-1 font-medium text-foreground/80">
                          <Sparkles className="h-3 w-3 text-amber-500" />
                          上一轮（第 {latest.iteration} 轮）参考
                        </p>
                        <p className="mt-1">
                          {latest.score != null && <>评分：<strong>{latest.score.toFixed(1)}</strong> · </>}
                          状态：{statusLabel[latest.status] || latest.status}
                          {latest.k8s_summary && <> · {latest.k8s_summary}</>}
                        </p>
                        {latest.report_excerpt && (
                          <p className="mt-1 line-clamp-2">{latest.report_excerpt.slice(0, 200)}</p>
                        )}
                      </div>
                    )}
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">本轮标题（可覆盖）</label>
                      <Input value={nextTitle} onChange={(e) => setNextTitle(e.target.value)}
                        placeholder={latest?.title || data.name} />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">研究目标（可覆盖）</label>
                      <Textarea value={nextGoal} onChange={(e) => setNextGoal(e.target.value)} rows={3}
                        placeholder={isFirstRound ? `对「${data.name}」进行系统性预研...` : latest?.goal} />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">K8s 环境验证</label>
                      <div className="flex items-center gap-2">
                        {[
                          { v: -1, label: "关闭", desc: "不进行集群实测" },
                          { v: 0, label: "自动", desc: "按目标自动判断" },
                          { v: 1, label: "开启", desc: "强制集群实测" },
                        ].map((o) => (
                          <button key={o.v} type="button"
                            onClick={() => setNextK8s(nextK8s === o.v ? null : o.v)}
                            title={o.desc}
                            className={"rounded border px-2 py-1 text-[11px] transition-colors " +
                              (nextK8s === o.v
                                ? "border-primary bg-primary/10 text-foreground"
                                : "border-border bg-background text-muted-foreground hover:bg-muted")}>
                            {o.label}
                          </button>
                        ))}
                        <span className="text-[10px] text-muted-foreground/70">
                          当前：{latest?.requires_k8s_validation === 1 ? "开启" : latest?.requires_k8s_validation === -1 ? "关闭" : "自动"}
                        </span>
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">约束条件（可覆盖）</label>
                      <Textarea value={nextConstraints} onChange={(e) => setNextConstraints(e.target.value)} rows={2}
                        placeholder={latest?.constraints || "（无）"} />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">预期产出</label>
                      <Textarea value={nextOutput} onChange={(e) => setNextOutput(e.target.value)} rows={2}
                        placeholder={latest?.expected_output || "（无）"} />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">说明（commit message）</label>
                      <Input value={commitMsg} onChange={(e) => setCommitMsg(e.target.value)}
                        placeholder={isFirstRound ? "如：首轮研究，确定基线" : "如：第1轮发现哨兵扩展性差，本轮转向 Cluster"} />
                    </div>
                    <Button type="submit" disabled={iterate.isPending} className="w-full">
                      {iterate.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                      {isFirstRound ? "启动第 1 轮研究" : `启动第 ${sessions.length + 1} 轮研究`}
                    </Button>
                  </form>
                </CardContent>
                </Card>
              )}
            </div>
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
                {latest.score != null && (
                  <div className="flex justify-between"><span className="text-muted-foreground">评分</span>
                    <Badge variant={latest.score >= 8 ? "success" : latest.score >= 6 ? "warning" : "destructive"}>{latest.score.toFixed(1)}</Badge>
                  </div>
                )}
                {latest.k8s_summary && (
                  <div className="rounded border border-cyan-500/30 bg-cyan-500/5 p-2">
                    <p className="text-[10px] text-cyan-600 dark:text-cyan-300">{latest.k8s_summary}</p>
                  </div>
                )}
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

/** 基线概览：第1轮为基线，展示评分趋势、相对基线的变化、平均分等指标。 */
function BaselineOverview({ data, sessions }: { data: any; sessions: TopicSession[] }) {
  const trend = data.score_trend as (number | null)[];
  const baselineScore = data.baseline?.score;
  const latestScore = data.latest_score;
  const delta = data.delta_from_baseline;
  const improved = data.improved;
  const avgScore = data.avg_score;
  const bestIter = data.best_iteration;
  const bestScore = data.best_score;

  const maxScore = Math.max(10, ...(trend.filter((s): s is number => s != null)));

  return (
    <Card className="border-blue-500/20">
      <CardContent className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* Left: key metrics */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-blue-500" />
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                基线概览
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <div className="rounded border bg-muted/40 px-3 py-1.5">
                <p className="text-[10px] text-muted-foreground">基线评分（第1轮）</p>
                <p className="font-bold">{baselineScore != null ? baselineScore.toFixed(1) : "—"}</p>
              </div>
              <div className="rounded border bg-muted/40 px-3 py-1.5">
                <p className="text-[10px] text-muted-foreground">最新评分</p>
                <p className="font-bold">{latestScore != null ? latestScore.toFixed(1) : "—"}</p>
              </div>
              <div className="rounded border px-3 py-1.5"
                   style={{ borderColor: improved ? "rgb(16 185 129 / 0.4)" : "rgb(245 158 11 / 0.4)",
                            background: improved ? "rgb(16 185 129 / 0.05)" : "rgb(245 158 11 / 0.05)" }}>
                <p className="text-[10px] text-muted-foreground">相对基线变化</p>
                <p className={"font-bold " + (improved ? "text-emerald-500" : delta != null && delta < 0 ? "text-amber-500" : "")}>
                  {delta == null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}${improved ? " ↑" : delta < 0 ? " ↓" : ""}`}
                </p>
              </div>
              <div className="rounded border bg-muted/40 px-3 py-1.5">
                <p className="text-[10px] text-muted-foreground">平均分</p>
                <p className="font-bold">{avgScore != null ? avgScore.toFixed(1) : "—"}</p>
              </div>
              <div className="rounded border bg-muted/40 px-3 py-1.5">
                <p className="text-[10px] text-muted-foreground">最佳轮次</p>
                <p className="font-bold">{bestIter != null ? `第 ${bestIter} 轮` : "—"}
                  {bestScore != null && <span className="ml-1 text-[10px] font-normal text-muted-foreground">({bestScore.toFixed(1)})</span>}
                </p>
              </div>
            </div>
          </div>

          {/* Right: score trend chart */}
          <div className="min-w-[220px] flex-1">
            <p className="mb-1 text-[10px] font-medium text-muted-foreground">评分趋势（各轮 vs 基线）</p>
            <div className="flex h-24 items-end gap-1.5">
              {trend.map((s, i) => {
                const v = s as number | null;
                const isBaseline = i === 0;
                const h = v != null ? Math.max(6, (v / maxScore) * 100) : 4;
                return (
                  <div key={i} className="flex flex-1 flex-col items-center gap-1">
                    <div className="flex w-full flex-1 items-end">
                      <div
                        className="w-full rounded-t"
                        style={{
                          height: `${h}%`,
                          background: v == null
                            ? "rgb(113 113 122 / 0.2)"
                            : isBaseline
                              ? "rgb(59 130 246 / 0.8)"
                              : v >= 8
                                ? "rgb(16 185 129 / 0.8)"
                                : v >= 6
                                  ? "rgb(245 158 11 / 0.8)"
                                  : "rgb(239 68 68 / 0.8)",
                        }}
                      />
                    </div>
                    <span className="text-[9px] text-muted-foreground">第{i + 1}轮</span>
                    {v != null && <span className="text-[9px] font-medium tabular-nums">{v.toFixed(1)}</span>}
                  </div>
                );
              })}
            </div>
            {baselineScore != null && (
              <p className="mt-1 text-[9px] text-muted-foreground">
                <span className="mr-2 inline-block h-2 w-2 rounded-sm bg-blue-500/80" />
                第1轮为基线，后续轮次与之对比
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
