"use client";
import { useState, useMemo } from "react";
import Link from "next/link";
import {
  ArrowLeft, Copy, Check, Download, FileText, GitBranch,
  BarChart3, CheckCircle2, AlertCircle, Sparkles, Loader2, Trophy,
  RotateCcw, Clock, Hash, List, TrendingUp, TrendingDown, Minus,
  AlertTriangle, HelpCircle, ListChecks, Quote, BookOpen, MessageSquareWarning,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { lazy, Suspense } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { REVIEW_DIMENSION_LABELS } from "@/lib/labels";
import { reportApi } from "../api-report";
import type { Report, ReportSection } from "../api-report";
import type { TaskNode } from "@/lib/types";

// Dynamic imports for heavy libraries (mermaid + react-markdown)
const MarkdownRender = lazy(() =>
  import("./markdown-render").then(m => ({ default: m.MarkdownRender }))
);
const MermaidRender = lazy(() =>
  import("./mermaid-render").then(m => ({ default: m.MermaidRender }))
);
const DynamicFlowDiagram = lazy(() =>
  import("./dynamic-flow-diagram").then(m => ({ default: m.DynamicFlowDiagram }))
);

function DownloadButton({ content, filename, label }: { content: string; filename: string; label: string }) {
  const onDownload = () => {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };
  return (
    <Button variant="outline" size="sm" onClick={onDownload}>
      <Download className="h-3.5 w-3.5" />
      {label}
    </Button>
  );
}

function ScoreBar({ label, score, threshold, max = 10 }: { label: string; score: number; threshold: number; max?: number }) {
  const ok = score >= threshold;
  const pct = Math.min(100, (score / max) * 100);
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-32 shrink-0 text-muted-foreground">{REVIEW_DIMENSION_LABELS[label] || label.replace(/_/g, " ")}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={"h-full transition-all " + (ok ? "bg-emerald-500" : "bg-amber-500")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={"w-10 text-right font-mono text-[11px] " + (ok ? "text-emerald-600" : "text-amber-600")}>
        {score.toFixed(1)}
      </span>
    </div>
  );
}

// Radar chart for 6 review dimensions (pure SVG, no extra deps)
function ReviewRadar({ dimensions, threshold }: { dimensions: Record<string, number>; threshold: number }) {
  const keys = Object.keys(dimensions);
  const cx = 100, cy = 100, r = 70;
  const angle = (i: number) => (Math.PI * 2 * i) / keys.length - Math.PI / 2;
  const point = (i: number, value: number) => {
    const a = angle(i);
    const dist = (value / 10) * r;
    return [cx + Math.cos(a) * dist, cy + Math.sin(a) * dist] as const;
  };

  const scorePoints = keys.map((_, i) => point(i, dimensions[keys[i]]));
  const thresholdPoints = keys.map((_, i) => point(i, threshold));

  return (
    <svg viewBox="0 0 200 200" className="h-48 w-full">
      {[2, 4, 6, 8, 10].map(v => (
        <circle key={v} cx={cx} cy={cy} r={(v / 10) * r} fill="none" stroke="currentColor" className="text-muted" strokeOpacity={0.2} />
      ))}
      {keys.map((_, i) => {
        const [x, y] = point(i, 10);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="currentColor" className="text-muted" strokeOpacity={0.3} />;
      })}
      <polygon
        points={thresholdPoints.map(p => p.join(",")).join(" ")}
        fill="none"
        stroke="currentColor"
        className="text-amber-500"
        strokeWidth={1}
        strokeDasharray="3,3"
      />
      <polygon
        points={scorePoints.map(p => p.join(",")).join(" ")}
        fill="currentColor"
        className="text-emerald-500/30"
        stroke="currentColor"
        strokeWidth={2}
      />
      {scorePoints.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={3} fill="currentColor" className="text-emerald-500" />
      ))}
      {keys.map((k, i) => {
        const a = angle(i);
        const lr = r + 12;
        const x = cx + Math.cos(a) * lr;
        const y = cy + Math.sin(a) * lr;
        return (
          <text key={k} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fontSize="9" fill="currentColor" className="fill-muted-foreground">
            {(REVIEW_DIMENSION_LABELS[k] || k).slice(0, 6)}
          </text>
        );
      })}
    </svg>
  );
}

// Normalize a string-or-list field to a string list
function asList(v: unknown): string[] {
  if (!v) return [];
  if (Array.isArray(v)) return v.filter(s => typeof s === "string" && s.trim());
  if (typeof v === "string") {
    // Split on common delimiters
    const parts = v.split(/[；;。]/).map(s => s.trim()).filter(Boolean);
    return parts.length > 0 ? parts : [v];
  }
  return [];
}

// Get the best available strengths/weaknesses list from review
function getStrengths(review: Report["review"]): string[] {
  if (!review) return [];
  return asList(review.strengths_list || review.strengths);
}
function getWeaknesses(review: Report["review"]): string[] {
  if (!review) return [];
  return asList(review.weaknesses_list || review.weaknesses);
}

// Report metadata stats
function ReportStats({ sections, reportMarkdown }: { sections: any; reportMarkdown?: string }) {
  const allText = (sections.executive_summary || "") + (sections.comparison_table || "") + (reportMarkdown || "");
  const charCount = allText.length;
  const readingMin = Math.max(1, Math.round(charCount / 400));
  const sectionCount = (reportMarkdown?.match(/^##\s+\d+\.\s/gm) || []).length;

  return (
    <div className="grid grid-cols-3 gap-3 text-center">
      <div className="rounded-md border bg-muted/30 p-2">
        <p className="text-2xl font-semibold">{charCount}</p>
        <p className="text-[10px] text-muted-foreground">字符数</p>
      </div>
      <div className="rounded-md border bg-muted/30 p-2">
        <p className="text-2xl font-semibold">{readingMin}</p>
        <p className="text-[10px] text-muted-foreground">分钟阅读</p>
      </div>
      <div className="rounded-md border bg-muted/30 p-2">
        <p className="text-2xl font-semibold">{sectionCount}</p>
        <p className="text-[10px] text-muted-foreground">章节</p>
      </div>
    </div>
  );
}

// TOC sidebar with all 5 tabs
function TableOfContents({ sections, fullReport, onNavigate }: { sections: ReportSection; fullReport?: string | null; onNavigate?: (id: string) => void }) {
  const items: { id: string; tab: string; label: string; available: boolean }[] = [
    { id: "summary", tab: "summary", label: "Executive Summary", available: !!sections.executive_summary },
    { id: "full", tab: "full", label: "完整报告（12 节）", available: !!fullReport },
    { id: "diagram", tab: "diagram", label: "研究流程", available: !!sections.research_flow_diagram },
    { id: "compare", tab: "compare", label: "Candidate 对比", available: !!sections.comparison_table },
    { id: "review", tab: "review", label: "AI 评审", available: true },
  ];

  return (
    <Card className="sticky top-4">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-1.5 text-xs font-medium">
          <List className="h-3 w-3" />
          目录
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 pt-0">
        {items.map(item => (
          <button
            key={item.id}
            onClick={() => onNavigate?.(item.tab)}
            disabled={!item.available}
            className={
              "flex w-full items-center gap-1.5 rounded-sm px-2 py-1 text-left text-xs transition-colors " +
              (item.available
                ? "text-foreground hover:bg-muted cursor-pointer"
                : "text-muted-foreground/50 cursor-not-allowed")
            }
          >
            <span className="h-1 w-1 rounded-full bg-current" />
            {item.label}
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

export function ReportView({ report }: { report: Report }) {
  const { data: tasks } = useQuery({
    queryKey: ["research-tasks", report.research.id],
    queryFn: () => api.get<TaskNode[]>(`/api/v1/researches/${report.research.id}/tasks`),
    refetchInterval: 5000,
  });
  const [tab, setTab] = useState("summary");
  const [regenerating, setRegenerating] = useState(false);
  const queryClient = useQueryClient();
  const onRegenerate = async () => {
    if (regenerating) return;
    if (!confirm("重新生成报告会调用 LLM（消耗 token），确定继续？")) return;
    setRegenerating(true);
    try {
      await reportApi.regenerate(report.research.id);
      // Invalidate the report query to refetch
      queryClient.invalidateQueries({ queryKey: ["report", report.research.id] });
      queryClient.invalidateQueries({ queryKey: ["research-report", report.research.id] });
    } catch (e) {
      alert(`重新生成失败: ${(e as Error).message}`);
    } finally {
      setRegenerating(false);
    }
  };
  const review = report.review;
  const sections = report.sections;
  const overall = review?.overall_score ?? 0;
  const passed = review ? overall >= review.threshold : false;

  const fullMarkdown = report.full_report || sections.executive_summary || "";

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_200px]">
      <div className="space-y-6">
        {/* Header card with stats */}
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <Trophy className={"h-4 w-4 " + (passed ? "text-emerald-500" : "text-amber-500")} />
                  <CardTitle className="text-base">最终研究报告</CardTitle>
                  {passed ? (
                    <Badge variant="success" className="h-5">通过阈值</Badge>
                  ) : (
                    <Badge variant="warning" className="h-5">未达阈值</Badge>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  生成于 {new Date(report.research.updated_at).toLocaleString()} ·
                  深度：{report.research.depth} · Priority：{report.research.priority}
                </p>
              </div>
              {review && (
                <div className="text-right">
                  <p className="text-3xl font-bold tracking-tight">{overall.toFixed(1)}</p>
                  <p className="text-[10px] text-muted-foreground">/ {review.threshold.toFixed(1)} 阈值</p>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="border-t pt-4">
            <ReportStats sections={sections} reportMarkdown={fullMarkdown} />
          </CardContent>
        </Card>

        {/* Truncation warning + regenerate */}
        {report.is_truncated && (
          <Card className="border-orange-500/40 bg-orange-500/5">
            <CardContent className="py-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-orange-600" />
                <div className="flex-1 space-y-2">
                  <p className="text-sm font-medium text-orange-700 dark:text-orange-300">
                    报告在生成时被 LLM 的 token 限制截断，内容不完整
                  </p>
                  <p className="text-xs text-muted-foreground">
                    点击下方按钮重新生成完整报告（会调用 LLM 一次，约 30-60 秒）。
                  </p>
                  <Button
                    size="sm"
                    variant="default"
                    disabled={regenerating}
                    onClick={onRegenerate}
                    className="mt-1"
                  >
                    <RotateCcw className={"mr-1.5 h-3.5 w-3.5 " + (regenerating ? "animate-spin" : "")} />
                    {regenerating ? "正在重新生成..." : "重新生成完整报告"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Verdict banner */}
        {review?.verdict && (
          <Card className={passed ? "border-emerald-500/30 bg-emerald-500/5" : "border-amber-500/30 bg-amber-500/5"}>
            <CardContent className="py-3">
              <div className="flex items-start gap-3">
                <Quote className={"mt-0.5 h-4 w-4 shrink-0 " + (passed ? "text-emerald-600" : "text-amber-600")} />
                <div className="flex-1">
                  <p className={"text-xs font-medium " + (passed ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300")}>
                    评审员结论
                  </p>
                  <p className="mt-1 text-sm leading-relaxed">{review.verdict}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="summary">
              <FileText className="mr-1 h-3 w-3" /> 摘要
            </TabsTrigger>
            <TabsTrigger value="full">
              <BookOpen className="mr-1 h-3 w-3" /> 完整报告
            </TabsTrigger>
            <TabsTrigger value="diagram">
              <GitBranch className="mr-1 h-3 w-3" /> 流程
            </TabsTrigger>
            <TabsTrigger value="compare">
              <BarChart3 className="mr-1 h-3 w-3" /> 对比
            </TabsTrigger>
            <TabsTrigger value="review">
              <Sparkles className="mr-1 h-3 w-3" /> 评审
            </TabsTrigger>
          </TabsList>

          <TabsContent value="summary" className="mt-4">
            <Card id="card-summary">
              <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
                <CardTitle className="text-base">Executive Summary</CardTitle>
                {sections.executive_summary && (
                  <DownloadButton
                    content={sections.executive_summary}
                    filename={`${report.research.title.replace(/\s+/g, "-").toLowerCase()}-summary.md`}
                    label="下载 .md"
                  />
                )}
              </CardHeader>
              <CardContent>
                {sections.executive_summary ? (
                  <Suspense fallback={<p className="p-4 text-xs text-muted-foreground">加载报告…</p>}><MarkdownRender content={sections.executive_summary} /></Suspense>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">暂无报告内容。</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="full" className="mt-4">
            <Card id="card-full">
              <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
                <CardTitle className="text-base">完整研究报告</CardTitle>
                {fullMarkdown && (
                  <DownloadButton
                    content={fullMarkdown}
                    filename={`${report.research.title.replace(/\s+/g, "-").toLowerCase()}.md`}
                    label="下载完整 .md"
                  />
                )}
              </CardHeader>
              <CardContent>
                {fullMarkdown ? (
                  <Suspense fallback={<p className="p-4 text-xs text-muted-foreground">加载报告…</p>}>
                    <MarkdownRender content={fullMarkdown} />
                  </Suspense>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">暂无报告内容。</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="diagram" className="mt-4">
            <Card id="card-diagram">
              <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
                <CardTitle className="text-base">研究流程 Diagram</CardTitle>
                {sections.research_flow_diagram && (
                  <DownloadButton
                    content={sections.research_flow_diagram}
                    filename={`${report.research.title.replace(/\s+/g, "-").toLowerCase()}.mmd`}
                    label="Mermaid (.mmd)"
                  />
                )}
              </CardHeader>
              <CardContent>
                {sections.research_flow_diagram ? (
                  <div className="rounded-md border bg-background p-4">
                    <Suspense fallback={<p className="p-4 text-xs text-muted-foreground">加载图表…</p>}><DynamicFlowDiagram tasks={tasks as any} researchStatus={report.research.status} /></Suspense>
                  </div>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">暂无流程图。</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="compare" className="mt-4">
            <Card id="card-compare">
              <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
                <CardTitle className="text-base">Candidate 对比分析</CardTitle>
                {sections.comparison_table && (
                  <DownloadButton
                    content={sections.comparison_table}
                    filename={`${report.research.title.replace(/\s+/g, "-").toLowerCase()}-compare.md`}
                    label="下载 .md"
                  />
                )}
              </CardHeader>
              <CardContent>
                {sections.comparison_table ? (
                  <Suspense fallback={<p className="p-4 text-xs text-muted-foreground">加载对比…</p>}><MarkdownRender content={sections.comparison_table} /></Suspense>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">暂无对比表。</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="review" className="mt-4">
            <Card id="card-review">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="h-4 w-4" />
                  AI 智能评审 Evaluation
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {review ? (
                  <>
                    {/* Scores + Radar */}
                    <div className="grid gap-6 md:grid-cols-[1fr_240px]">
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-muted-foreground">各维度评分</p>
                        {Object.entries(review.dimensions).map(([k, v]) => (
                          <ScoreBar key={k} label={k} score={v} threshold={review.threshold} />
                        ))}
                      </div>
                      <div className="rounded-md border bg-muted/30 p-2">
                        <p className="mb-1 text-center text-xs font-medium text-muted-foreground">6 维雷达</p>
                        <ReviewRadar dimensions={review.dimensions} threshold={review.threshold} />
                      </div>
                    </div>

                    <Separator />

                    {/* Structured feedback */}
                    <div className="space-y-4">
                      {/* Strengths */}
                      {(() => {
                        const strs = getStrengths(review);
                        if (strs.length === 0) return null;
                        return (
                          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-4">
                            <p className="mb-2 text-xs font-medium text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5">
                              <CheckCircle2 className="h-3.5 w-3.5" /> 优势 ({strs.length})
                            </p>
                            <ul className="space-y-1.5 text-xs leading-relaxed text-foreground/90">
                              {strs.map((s, i) => (
                                <li key={i} className="flex gap-2">
                                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-emerald-500" />
                                  <span>{s}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        );
                      })()}

                      {/* Weaknesses */}
                      {(() => {
                        const wks = getWeaknesses(review);
                        if (wks.length === 0) return null;
                        return (
                          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-4">
                            <p className="mb-2 text-xs font-medium text-amber-700 dark:text-amber-300 flex items-center gap-1.5">
                              <AlertTriangle className="h-3.5 w-3.5" /> 不足 ({wks.length})
                            </p>
                            <ul className="space-y-1.5 text-xs leading-relaxed text-foreground/90">
                              {wks.map((s, i) => (
                                <li key={i} className="flex gap-2">
                                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                                  <span>{s}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        );
                      })()}

                      {/* Improvements (actionable) */}
                      {(() => {
                        const imps = review.improvements || [];
                        if (imps.length === 0) return null;
                        return (
                          <div className="rounded-md border border-blue-500/30 bg-blue-500/5 p-4">
                            <p className="mb-2 text-xs font-medium text-blue-700 dark:text-blue-300 flex items-center gap-1.5">
                              <ListChecks className="h-3.5 w-3.5" /> 改进建议 ({imps.length})
                            </p>
                            <ul className="space-y-1.5 text-xs leading-relaxed text-foreground/90">
                              {imps.map((s, i) => (
                                <li key={i} className="flex gap-2">
                                  <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-blue-500/15 font-mono text-[10px] text-blue-700 dark:text-blue-300">{i+1}</span>
                                  <span>{s}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        );
                      })()}

                      {/* Critical Questions */}
                      {(() => {
                        const qs = review.critical_questions || [];
                        if (qs.length === 0) return null;
                        return (
                          <div className="rounded-md border border-purple-500/30 bg-purple-500/5 p-4">
                            <p className="mb-2 text-xs font-medium text-purple-700 dark:text-purple-300 flex items-center gap-1.5">
                              <HelpCircle className="h-3.5 w-3.5" /> 关键问题（需先回答）({qs.length})
                            </p>
                            <ul className="space-y-1.5 text-xs leading-relaxed text-foreground/90">
                              {qs.map((s, i) => (
                                <li key={i} className="flex gap-2">
                                  <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-purple-500/15 font-mono text-[10px] text-purple-700 dark:text-purple-300">Q{i+1}</span>
                                  <span>{s}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        );
                      })()}

                      {/* Next Steps */}
                      {(() => {
                        const steps = review.next_steps || [];
                        if (steps.length === 0) return null;
                        return (
                          <div className="rounded-md border bg-muted/30 p-4">
                            <p className="mb-2 text-xs font-medium flex items-center gap-1.5">
                              <MessageSquareWarning className="h-3.5 w-3.5" /> 后续行动 ({steps.length})
                            </p>
                            <ul className="space-y-1.5 text-xs leading-relaxed text-foreground/90">
                              {steps.map((s, i) => (
                                <li key={i} className="flex gap-2">
                                  <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-md bg-foreground/10 font-mono text-[10px]">→</span>
                                  <span>{s}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        );
                      })()}

                      {/* Legacy single-string suggestions as fallback */}
                      {!review.improvements?.length && review.suggestions && (
                        <div className="rounded-md border bg-muted/50 p-3">
                          <p className="text-xs font-medium flex items-center gap-1.5">
                            <Sparkles className="h-3.5 w-3.5" /> 建议
                          </p>
                          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{review.suggestions}</p>
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">暂无评审。</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      <div className="hidden lg:block">
        <TableOfContents sections={sections} fullReport={fullMarkdown} onNavigate={setTab} />
      </div>
    </div>
  );
}

export function ReportSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-96 w-full" />
    </div>
  );
}

export function ReportError({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="py-12 text-center text-sm text-destructive">
        Failed to load report: {message}
      </CardContent>
    </Card>
  );
}
