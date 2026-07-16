"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2, FlaskConical, Sparkles, ChevronDown, CheckCircle2, AlertCircle, Wand2, X, FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useCreateResearch } from "../hooks";
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
  const [form, setForm] = React.useState({
    title: "",
    goal: "",
    constraints: "",
    expected_output: "",
    depth: "standard" as Depth,
    priority: "medium" as Priority,
    estimated_cost: 8,
  });
  const [templatesOpen, setTemplatesOpen] = React.useState(false);

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
