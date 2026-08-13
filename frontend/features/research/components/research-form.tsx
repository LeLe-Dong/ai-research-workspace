"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2, FlaskConical, Sparkles, ChevronDown, CheckCircle2, AlertCircle, Wand2, X, FileText, Server, BookOpen, ChevronRight } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useCreateResearch } from "../hooks";
import { useQuery } from "@tanstack/react-query";
import { knowledgeApi, type KnowledgeStyle } from "@/features/knowledge/api";
import { useExpandGoal } from "../hooks-expand";
import type { Depth, Priority } from "@/lib/types";
import { TEMPLATES, type ResearchTemplate } from "../data/templates";
import { smartExpandGoal, addStructure, isGoalDetailed } from "../data/smart-expand";
import { cn } from "@/lib/utils";

const depths: { value: Depth; label: string; desc: string }[] = [
  { value: "quick", label: "Quick", desc: "5 分钟 · ~3 来源" },
  { value: "standard", label: "Standard", desc: "15 分钟 · ~12 来源" },
  { value: "deep", label: "Deep", desc: "60 分钟 · ~30 来源" },
];

const priorities: { value: Priority; label: string; variant: "secondary" | "info" | "warning" }[] = [
  { value: "low", label: "低", variant: "secondary" },
  { value: "medium", label: "中", variant: "info" },
  { value: "high", label: "高", variant: "warning" },
];

export function ResearchForm() {
  const router = useRouter();
  const create = useCreateResearch();

  // Phase B: load available styles so user can pick a per-research style.
  const { data: stylesData } = useQuery({
    queryKey: ["knowledge", "styles"],
    queryFn: () => knowledgeApi.listStyles(),
  });
  const availableStyles: KnowledgeStyle[] = stylesData?.items ?? [];
  const [form, setForm] = React.useState({
    title: "",
    goal: "",
    constraints: "",
    expected_output: "",
    depth: "standard" as Depth,
    priority: "medium" as Priority,
    estimated_cost: 8,
    requires_k8s_validation: 0, // -1=off, 0=auto, 1=on
    use_custom_style: 0,        // 0=default 14-dim, 1=use a KnowledgeStyle
    style_id: null as string | null,  // Phase B: null = use currently active style
  });
  const selectedStylePreview = availableStyles.find((s) => s.id === form.style_id);
  const [templatesOpen, setTemplatesOpen] = React.useState(false);
  // "一句话生成" state: subject input + generated plan preview.
  const [quickOpen, setQuickOpen] = React.useState(false);
  const [subject, setSubject] = React.useState("");
  const [generated, setGenerated] = React.useState<{ plan: any; source: string } | null>(null);
  const [generating, setGenerating] = React.useState(false);
  const generatePlan = React.useCallback(async () => {
    const s = subject.trim();
    if (!s) { toast.error("请先输入一句话研究主题"); return; }
    setGenerating(true);
    try {
      const { useGeneratePlan } = await import("@/features/topics/hooks");
      // use hooks imperatively is awkward; call API directly via lib/api.
      const { api } = await import("@/lib/api");
      const data = await api.post<any>("/api/v1/researches/generate-plan", { subject: s, use_llm: true });
      setGenerated({ plan: data.plan, source: data.source });
      toast.success("已生成研究方案，可预览后提交");
    } catch (e) {
      toast.error("生成失败", { description: (e as Error).message });
    } finally {
      setGenerating(false);
    }
  }, [subject]);

  const applyGenerated = () => {
    if (!generated) return;
    const p = generated.plan;
    setForm((f) => ({
      ...f,
      title: p.title || f.title,
      goal: p.goal || f.goal,
      constraints: p.constraints || f.constraints,
      expected_output: p.expected_output || f.expected_output,
      depth: (["quick", "standard", "deep"].includes(p.depth) ? p.depth : f.depth) as Depth,
      priority: (["low", "medium", "high"].includes(p.priority) ? p.priority : f.priority) as Priority,
      requires_k8s_validation: typeof p.requires_k8s_validation === "number" ? p.requires_k8s_validation : f.requires_k8s_validation,
    }));
    setQuickOpen(false);
    toast.success("已填入表单", { description: "可继续修改后提交" });
  };

  // Phase B-2: Auto-suggest best-matching style when goal / constraints change.
  // Debounced 600ms so we don't fire on every keystroke.
  const [suggestedStyles, setSuggestedStyles] = React.useState<
    Array<{ style: import("@/features/knowledge/api").KnowledgeStyle; score: number }>
  >([]);
  React.useEffect(() => {
    const t = setTimeout(async () => {
      const goal = (form.goal || "").trim();
      const cons = (form.constraints || "").trim();
      if (goal.length < 4) { setSuggestedStyles([]); return; }
      try {
        const m = await knowledgeApi.matchStyles(goal, cons);
        setSuggestedStyles(m.matches.map((x) => ({ style: x.style, score: x.score })));
      } catch { /* silent */ }
    }, 600);
    return () => clearTimeout(t);
  }, [form.goal, form.constraints]);

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const applyTemplate = (t: ResearchTemplate) => {
    setForm((f) => ({
      ...f,
      title: t.title,
      goal: t.goal,
      constraints: t.constraints || f.constraints,
      expected_output: t.expected_output || f.expected_output,
      depth: t.depth || f.depth,
      priority: t.priority || f.priority,
    }));
    setTemplatesOpen(false);
    toast.success("已应用模板", { description: t.title });
  };

  const { expand: llmExpand, isExpanding, error: expandError } = useExpandGoal();

  const aiOptimize = async () => {
    if (!form.goal.trim()) {
      toast.error("请先填写研究目标");
      return;
    }
    // Try LLM expansion first
    const result = await llmExpand(form.goal);
    if (result) {
      set("goal", result.expanded);
      toast.success("AI 优化完成", {
        description: result.cached
          ? "（来自缓存）"
          : `由 ${result.model} 生成 · ${result.tokens_used ?? "?"} tokens`,
      });
      return;
    }
    // LLM failed - fall back to heuristic
    if (expandError) {
      // Common error cases
      if (expandError.includes("未启用") || expandError.includes("AIRW_STEPFUN")) {
        toast.warning("AI 优化未配置", {
          description: "使用本地启发式扩写",
          duration: 4000,
        });
      } else if (expandError.includes("超时")) {
        toast.error("AI 服务超时", { description: "使用本地启发式扩写" });
      } else {
        toast.warning("AI 优化失败", {
          description: "已使用本地启发式扩写",
        });
      }
    }
    // Fallback to heuristic
    const expanded = smartExpandGoal(form.goal);
    if (expanded === form.goal) {
      set("goal", addStructure(form.goal));
      toast.info("已添加结构", { description: "你可以进一步修改" });
    } else {
      set("goal", expanded);
      toast.info("本地扩写完成", { description: "AI 不可用，使用了规则模板" });
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim() || !form.goal.trim()) {
      toast.error("标题 and 研究目标 are required.");
      return;
    }
    // Pre-submit quality check
    const check = isGoalDetailed(form.goal);
    if (!check.ok) {
      toast.warning("目标可能不够详细", {
        description: check.reason,
        duration: 5000,
      });
    }
    try {
      const r = await create.mutateAsync(form);
      toast.success("研究已创建", { description: r.title });
      router.push(`/research/${r.id}`);
    } catch (err) {
      toast.error("创建研究失败", {
        description: (err as Error).message,
      });
    }
  };

  // Group templates by category
  const groupedTemplates = React.useMemo(() => {
    const groups: Record<string, ResearchTemplate[]> = {};
    for (const t of TEMPLATES) {
      if (!groups[t.category]) groups[t.category] = [];
      groups[t.category].push(t);
    }
    return groups;
  }, []);

  // Quality indicator
  const goalQuality = isGoalDetailed(form.goal);

  return (
    <form onSubmit={submit} className="space-y-4">
      {/* Quick generate: one-line subject → full plan */}
      <Card className="border-dashed bg-gradient-to-r from-indigo-500/5 to-purple-500/5">
        <CardContent className="p-3">
          <div className="flex items-center gap-3">
            <Wand2 className="h-4 w-4 text-purple-400" />
            <div className="flex-1">
              <p className="text-xs font-medium">AI 一句话生成研究方案</p>
              <p className="text-[10px] text-muted-foreground">
                只需一句主题（如"评估 Redis 集群高可用方案"），自动生成完整研究计划
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => setQuickOpen(!quickOpen)}>
              <Sparkles className="mr-1.5 h-3.5 w-3.5 text-purple-400" />
              {quickOpen ? "收起" : "开始生成"}
            </Button>
          </div>
          {quickOpen && (
            <div className="mt-3 space-y-3 border-t pt-3">
              <div className="flex gap-2">
                <Input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); generatePlan(); } }}
                  placeholder="输入一句话研究主题…"
                />
                <Button type="button" size="sm" onClick={generatePlan} disabled={generating}>
                  {generating ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Sparkles className="mr-1.5 h-3.5 w-3.5" />}
                  生成
                </Button>
              </div>
              {generated && (
                <div className="rounded-md border bg-background/60 p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium flex items-center gap-1.5">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      已生成方案
                    </p>
                    <span className="text-[10px] text-muted-foreground">来源: {generated.source}</span>
                  </div>
                  <p className="mt-2 text-sm font-medium">{generated.plan.title}</p>
                  <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{generated.plan.goal}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
                    <Badge variant="outline">{generated.plan.depth}</Badge>
                    <Badge variant="outline">优先级 {generated.plan.priority}</Badge>
                    <Badge variant="outline">k8s验证: {generated.plan.requires_k8s_validation === 1 ? "开" : generated.plan.requires_k8s_validation === -1 ? "关" : "自动"}</Badge>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Button type="button" size="sm" onClick={applyGenerated}>
                      <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                      填入表单
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => setGenerated(null)}>
                      <X className="mr-1.5 h-3.5 w-3.5" />
                      丢弃
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Template selector */}
      <Card className="border-dashed bg-muted/20">
        <CardContent className="p-3">
          <div className="flex items-center gap-3">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <div className="flex-1">
              <p className="text-xs font-medium">不知道从何写起？</p>
              <p className="text-[10px] text-muted-foreground">
                从 {TEMPLATES.length} 个常见研究模板开始，可随时修改
              </p>
            </div>
            <Popover open={templatesOpen} onOpenChange={setTemplatesOpen}>
              <PopoverTrigger asChild>
                <Button type="button" variant="outline" size="sm">
                  <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                  选择模板
                  <ChevronDown className="ml-1.5 h-3 w-3" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[480px] p-0" align="end">
                <div className="p-3 border-b">
                  <p className="text-sm font-medium">研究模板</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    点击模板自动填充表单，可继续修改
                  </p>
                </div>
                <div className="max-h-96 overflow-auto p-2">
                  {Object.entries(groupedTemplates).map(([category, items]) => (
                    <div key={category} className="mb-2">
                      <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        {category}
                      </p>
                      {items.map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => applyTemplate(t)}
                          className="w-full rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent"
                        >
                          <div className="flex items-start gap-2">
                            <span className="text-base">{t.icon}</span>
                            <div className="min-w-0 flex-1">
                              <p className="font-medium">{t.title}</p>
                              <p className="mt-0.5 line-clamp-2 text-[10px] text-muted-foreground">
                                {t.goal}
                              </p>
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </CardContent>
      </Card>

      {/* Block 1: Title + Goal */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <FlaskConical className="h-4 w-4" />
            研究目标
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="title">标题</Label>
            <Input
              id="title"
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
              placeholder="例：对比主流智能体编排框架"
              maxLength={200}
              required
            />
            <p className="text-xs text-muted-foreground">{form.title.length}/200</p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="goal" className="flex items-center gap-2">
                研究目标
                {form.goal && (
                  goalQuality.ok ? (
                    <span className="flex items-center gap-1 text-[10px] font-normal text-emerald-600">
                      <CheckCircle2 className="h-3 w-3" />
                      详细
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[10px] font-normal text-amber-600">
                      <AlertCircle className="h-3 w-3" />
                      可优化
                    </span>
                  )
                )}
              </Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={aiOptimize}
                disabled={!form.goal.trim() || isExpanding}
                className="h-6 px-2 text-xs"
              >
                {isExpanding ? (
                  <>
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    AI 思考中…
                  </>
                ) : (
                  <>
                    <Wand2 className="mr-1 h-3 w-3" />
                    AI 优化
                  </>
                )}
              </Button>
            </div>
            <Textarea
              id="goal"
              value={form.goal}
              onChange={(e) => set("goal", e.target.value)}
              placeholder={"例：对比 PostgreSQL 和 MySQL 在 1000+ 租户 SaaS 场景下的 OLTP 性能、运维成本和扩展性。给出推荐方案。"}
              rows={4}
              className="resize-y"
              required
            />
            {form.goal && !goalQuality.ok && (
              <p className="text-[10px] text-amber-600">💡 {goalQuality.reason}，或点击右上角"AI 优化"</p>
            )}
            {form.goal && goalQuality.ok && (
              <p className="text-[10px] text-emerald-600">✓ 目标已包含足够上下文</p>
            )}
            {isExpanding && (
              <p className="text-[10px] text-blue-600 animate-pulse">
                ✨ AI 正在分析你的目标，生成多维度问题…
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Block 2: Constraints + Output */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">约束条件 &amp; Output</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="constraints">约束条件</Label>
            <Textarea
              id="constraints"
              value={form.constraints}
              onChange={(e) => set("constraints", e.target.value)}
              placeholder={"例：必须本地部署；3 人工程师团队；6 周交付；预算 < $500/月。"}
              rows={2}
              className="resize-y"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="expected_output">预期输出</Label>
            <Textarea
              id="expected_output"
              value={form.expected_output}
              onChange={(e) => set("expected_output", e.target.value)}
              placeholder={"例：1) 对比矩阵 2) 推荐方案及理由 3) 90 天落地计划 4) 风险清单。"}
              rows={2}
              className="resize-y"
            />
          </div>
        </CardContent>
      </Card>

      {/* Block 3: Config */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">研究配置</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>研究深度</Label>
            <div className="grid grid-cols-3 gap-2">
              {depths.map((d) => (
                <button
                  key={d.value}
                  type="button"
                  onClick={() => set("depth", d.value)}
                  className={cn(
                    "rounded-md border p-2.5 text-left transition-colors",
                    form.depth === d.value
                      ? "border-primary bg-primary/5"
                      : "hover:bg-accent/50"
                  )}
                >
                  <div className="text-sm font-medium">{d.label}</div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">{d.desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label>优先级</Label>
            <div className="flex gap-2">
              {priorities.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => set("priority", p.value)}
                  className={cn(
                    "rounded-md border px-4 py-1.5 text-sm transition-colors",
                    form.priority === p.value
                      ? "border-primary bg-primary/5 font-medium"
                      : "hover:bg-accent/50"
                  )}
                >
                  <Badge variant={p.variant} className="mr-1 h-4 px-1 text-[10px]">
                    {p.label}
                  </Badge>
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="cost">预估成本（美元）</Label>
            <Input
              id="cost"
              type="number"
              min={0}
              step={0.5}
              value={form.estimated_cost}
              onChange={(e) => set("estimated_cost", parseFloat(e.target.value || "0"))}
              className="max-w-[160px]"
            />
            <p className="text-xs text-muted-foreground">
              演示引擎忽略成本字段；为未来保留。
            </p>
          </div>

          {/* K8s 环境验证三态选择 */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <Server className="h-3.5 w-3.5 text-cyan-600" />
              K8s 环境验证
            </Label>
            <div className="grid grid-cols-3 gap-2">
              {([
                { v: 0, label: "自动", desc: "智能判断", tone: "border-blue-500/40 bg-blue-500/5 text-blue-700 dark:text-blue-300" },
                { v: 1, label: "强制开启", desc: "集群测试", tone: "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300" },
                { v: -1, label: "强制关闭", desc: "跳过测试", tone: "border-zinc-500/40 bg-zinc-500/5 text-zinc-700 dark:text-zinc-300" },
              ] as const).map((o) => (
                <button
                  key={o.v}
                  type="button"
                  onClick={() => set("requires_k8s_validation", o.v)}
                  className={cn(
                    "rounded-md border px-2 py-2 text-left text-xs transition-colors",
                    form.requires_k8s_validation === o.v
                      ? o.tone + " ring-1 ring-primary/40"
                      : "border-border hover:bg-accent/30"
                  )}
                  title={
                    o.v === 0 ? "根据目标/输出/深度智能判断是否跑 k8s 验证" :
                    o.v === 1 ? "强制在真实集群部署 test pod 验证" :
                                  "完全跳过 k8s 验证阶段"
                  }
                >
                  <div className="font-medium">{o.label}</div>
                  <div className="text-[10px] opacity-70">{o.desc}</div>
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {form.requires_k8s_validation === 0 && "智能判断：检测目标/输出中的 K8s 相关关键词，结合 depth 综合决策"}
              {form.requires_k8s_validation === 1 && "强制开启：本次研究会在 airw-research 命名空间创建 test pod"}
              {form.requires_k8s_validation === -1 && "强制关闭：不会进行 K8s 集群验证"}
            </p>
          </div>

          {/* Personalized style toggle */}
          <div className="rounded-md border bg-muted/20 px-3 py-2.5">
            <label className="flex cursor-pointer items-start gap-2.5">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 shrink-0 accent-blue-500"
                checked={form.use_custom_style === 1}
                onChange={(e) => set("use_custom_style", e.target.checked ? 1 : 0)}
              />
              <div className="flex-1">
                <div className="flex items-center gap-1.5 text-xs font-medium">
                  <BookOpen className="h-3.5 w-3.5 text-blue-500" />
                  使用我的研究风格
                  <Link
                    href="/knowledge"
                    target="_blank"
                    className="ml-auto inline-flex items-center gap-0.5 text-[10px] font-normal text-muted-foreground hover:text-foreground"
                  >
                    管理风格 <ChevronRight className="h-3 w-3" />
                  </Link>
                </div>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {form.use_custom_style === 1
                    ? "本次研究将使用你在 /knowledge 上传并抽取的章节结构与写作风格。"
                    : "本次研究使用默认 14 维度评估框架。"}
                </p>
              </div>
            </label>
            {form.use_custom_style === 1 && (
              <div className="mt-2 border-t pt-2">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  选择风格版本（可创建多个风格用于不同场景）
                </p>
                <select
                  value={form.style_id ?? ""}
                  onChange={(e) =>
                    set("style_id", e.target.value === "" ? null : e.target.value)
                  }
                  className="w-full rounded-md border bg-background px-2 py-1 text-xs outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="">使用当前激活的风格（默认）</option>
                  {availableStyles.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} {s.is_active ? "（当前激活）" : ""} · {s.dimensions.length} 维度
                    </option>
                  ))}
                </select>
                {selectedStylePreview && (
                  <div className="mt-2 rounded-md border bg-background/60 px-2 py-1.5">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      风格预览 · {selectedStylePreview.dimensions.length} 个维度
                    </p>
                    <ol className="mt-1 grid grid-cols-2 gap-x-2 text-[11px]">
                      {selectedStylePreview.dimensions.slice(0, 10).map((d, i) => (
                        <li key={i} className="truncate">
                          <span className="text-muted-foreground tabular-nums">{i + 1}.</span> {d}
                        </li>
                      ))}
                    </ol>
                    {selectedStylePreview.dimensions.length > 10 && (
                      <p className="mt-1 text-[10px] text-muted-foreground">
                        +{selectedStylePreview.dimensions.length - 10} 更多
                      </p>
                    )}
                  </div>
                )}
                {/* Auto-suggest based on goal keywords */}
                {suggestedStyles.length > 0 && (
                  <div className="mt-2 rounded-md border border-blue-500/30 bg-blue-500/5 px-2 py-1.5">
                    <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                      <Sparkles className="h-2.5 w-2.5" />
                      基于目标的智能推荐
                    </p>
                    <div className="space-y-1">
                      {suggestedStyles.slice(0, 3).map(({ style, score }) => (
                        <button
                          key={style.id}
                          type="button"
                          onClick={() => set("style_id", style.id)}
                          className={cn(
                            "flex w-full items-center justify-between rounded px-2 py-1 text-left text-[11px] transition-colors",
                            form.style_id === style.id
                              ? "bg-blue-500/20 text-blue-700 dark:text-blue-300"
                              : "hover:bg-blue-500/10"
                          )}
                        >
                          <span className="flex min-w-0 items-center gap-1.5">
                            <span className={cn(
                              "shrink-0 rounded px-1 font-mono text-[9px]",
                              score >= 10 ? "bg-emerald-500/20 text-emerald-700"
                                            : score >= 4 ? "bg-blue-500/20 text-blue-700"
                                                          : "bg-zinc-500/20 text-zinc-600"
                            )}>
                              {score}
                            </span>
                            <span className="truncate">{style.name}</span>
                          </span>
                          <span className="shrink-0 text-[10px] text-muted-foreground">
                            {style.dimensions.length}维
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          演示智能体将在约 4 秒内生成 5 阶段计划 + 20 个时间线事件 + 3 个产物。
        </p>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          开始研究
        </Button>
      </div>
    </form>
  );
}
