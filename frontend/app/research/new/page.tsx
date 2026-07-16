"use client";
import { Sparkles, Lightbulb, BookOpen, Zap, Tag, Wand2 } from "lucide-react";

import { ResearchForm } from "@/features/research/components/research-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TIPS = [
  { icon: Lightbulb, title: "具体目标", body: "目标越具体，LLM 检索越准。例如：「对比 PostgreSQL 和 TiDB 在 1000+ 租户场景下的 OLTP 表现」，而不是「数据库选型」。" },
  { icon: BookOpen, title: "明确约束", body: "团队规模、预算、已有技术栈、运维能力等。约束条件帮助 LLM 给出可落地的推荐而非空想。" },
  { icon: Zap, title: "指定输出", body: "例如：「3 年成本对比 + 部署架构图 + 12 周实施计划」。明确的输出形式能引导 LLM 输出对应内容。" },
];

const PROMPT_TIPS = [
  { icon: Wand2, title: "AI 优化", body: "如果不知道如何写详细，点击目标字段右上角「AI 优化」按钮，智能扩写为多维度问题。" },
  { icon: Tag, title: "选模板", body: "表单顶部「选择模板」可快速套用 8 个常见研究场景（选型/演进/诊断/架构/AI 等）。" },
];

export default function NewResearchPage() {
  return (
    <div className="container max-w-none px-6 py-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Left: form */}
        <div>
          <div className="mb-6">
            <h1 className="text-2xl font-semibold tracking-tight">新建研究</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              定义目标与约束。智能体将生成多阶段计划并自动执行。
            </p>
          </div>
          <ResearchForm />
        </div>

        {/* Right: tips */}
        <aside className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Sparkles className="h-4 w-4 text-amber-500" />
                高质量研究的特征
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {TIPS.map((t, i) => {
                const Icon = t.icon;
                return (
                  <div key={i} className="flex gap-3">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted">
                      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium">{t.title}</p>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{t.body}</p>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Wand2 className="h-4 w-4 text-blue-500" />
                不会写？试试这些
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {PROMPT_TIPS.map((t, i) => {
                const Icon = t.icon;
                return (
                  <div key={i} className="flex gap-3">
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-blue-500/10">
                      <Icon className="h-3 w-3 text-blue-600" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium">{t.title}</p>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{t.body}</p>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
