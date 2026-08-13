"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTopics, useCreateTopic } from "@/features/topics/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Layers, Plus, ArrowRight, Target, CheckCircle2, GitBranch, Loader2,
} from "lucide-react";

const statusLabel: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
};

export default function TopicsPage() {
  const router = useRouter();
  const { data, isLoading } = useTopics();
  const createTopic = useCreateTopic();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const r = await createTopic.mutateAsync({ name: name.trim(), description });
      router.push(`/topics/${r.id}`);
    } catch {
      /* toast handled in hook */
    }
  };

  return (
    <div className="container max-w-none px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Layers className="h-5 w-5 text-blue-500" />
            研究基线
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            同一研究主题可开展多轮研究：每轮完成后审核结论、调整研究边界，再启动下一轮
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/research/new">
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            新建研究
          </Link>
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        {/* Create topic form */}
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Plus className="h-4 w-4 text-emerald-500" />
              新建研究主题
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">主题名称 *</label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="如：Redis 集群高可用方案"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">一句话描述</label>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="该主题要研究什么（可选）"
                  rows={3}
                />
              </div>
              <Button type="submit" className="w-full" disabled={createTopic.isPending || !name.trim()}>
                {createTopic.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Target className="mr-2 h-4 w-4" />}
                创建并开始研究
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Topic list */}
        <div className="space-y-3">
          {isLoading ? (
            <Card><CardContent className="py-8 text-center text-xs text-muted-foreground">加载中...</CardContent></Card>
          ) : data && data.length > 0 ? (
            data.map((t) => (
              <Card key={t.id} className="hover:border-blue-500/40 transition-colors">
                <CardContent className="flex items-center gap-4 p-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">{t.name}</span>
                      <Badge variant="outline" className="text-xs shrink-0">
                        {t.iteration_count} 轮
                      </Badge>
                      {t.latest_status && (
                        <Badge variant={t.latest_status === "completed" ? "success" : "secondary"} className="text-xs shrink-0">
                          {statusLabel[t.latest_status]}
                        </Badge>
                      )}
                    </div>
                    {t.description && (
                      <p className="mt-1 truncate text-xs text-muted-foreground">{t.description}</p>
                    )}
                    <div className="mt-1.5 flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                        {t.completed_count} 轮完成
                      </span>
                      {t.latest_score != null && (
                        <span>最新评分 <strong className="text-amber-500">{t.latest_score}</strong></span>
                      )}
                    </div>
                  </div>
                  <Button asChild variant="ghost" size="sm">
                    <Link href={`/topics/${t.id}`}>
                      查看迭代
                      <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            ))
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <GitBranch className="mx-auto mb-3 h-8 w-8 text-muted-foreground/40" />
                <p className="text-sm text-muted-foreground">还没有研究主题</p>
                <p className="mt-1 text-xs text-muted-foreground/70">
                  在左侧创建一个主题，即可开始第一轮研究，之后可不断迭代调整
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
