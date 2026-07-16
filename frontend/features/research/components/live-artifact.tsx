"use client";
import { useState, useMemo, lazy, Suspense } from "react";
import { Download, FileText, GitBranch, BarChart3, CheckCircle2, Loader2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

import type { ArtifactOut, ReviewOut } from "@/lib/types";

// Dynamic imports for heavy libraries (mermaid ~200KB, react-markdown ~100KB)
const MermaidRender = lazy(() =>
  import("./mermaid-render").then(m => ({ default: m.MermaidRender }))
);
const MarkdownRender = lazy(() =>
  import("./markdown-render").then(m => ({ default: m.MarkdownRender }))
);

const ICON_FOR: Record<string, typeof FileText> = {
  mermaid: GitBranch,
  markdown: FileText,
  table: BarChart3,
  review: CheckCircle2,
};

function downloadArtifact(a: ArtifactOut) {
  const blob = new Blob([a.content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a2 = document.createElement("a");
  a2.href = url;
  const ext = a.kind === "mermaid" ? "mmd" : "md";
  a2.download = `${a.title.replace(/\s+/g, "-").toLowerCase()}.${ext}`;
  document.body.appendChild(a2);
  a2.click();
  document.body.removeChild(a2);
  URL.revokeObjectURL(url);
}

function RenderArtifact({ a }: { a: ArtifactOut }) {
  if (a.kind === "mermaid") {
    return (
      <Suspense fallback={<div className="p-4 text-center text-xs text-muted-foreground"><Loader2 className="inline h-3 w-3 animate-spin" /> 加载图表…</div>}>
        <MermaidRender code={a.content} />
      </Suspense>
    );
  }
  if (a.kind === "markdown" || a.kind === "table") {
    return (
      <Suspense fallback={<div className="p-4 text-center text-xs text-muted-foreground"><Loader2 className="inline h-3 w-3 animate-spin" /> 加载渲染…</div>}>
        <MarkdownRender content={a.content} />
      </Suspense>
    );
  }
  return <pre className="p-3 text-xs">{a.content}</pre>;
}

export function ReviewPanel({ review }: { review?: ReviewOut | null }) {
  if (!review) return null;
  const dims = review.dimensions || {};
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-baseline justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          智能评审 Score
        </p>
        <Badge variant={review.overall_score >= review.threshold ? "success" : "warning"} className="h-5 px-2 text-xs">
          {review.overall_score.toFixed(1)} / 10
        </Badge>
      </div>
      <div className="space-y-1.5">
        {Object.entries(dims).map(([k, v]) => {
          const score = v as number;
          return (
            <div key={k} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</span>
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                  <div
                    className={
                      "h-full " +
                      (score >= 8 ? "bg-emerald-500" : score >= 6 ? "bg-amber-500" : "bg-destructive")
                    }
                    style={{ width: `${score * 10}%` }}
                  />
                </div>
                <span className="w-8 text-right font-mono text-[10px]">{score.toFixed(1)}</span>
              </div>
            </div>
          );
        })}
      </div>
      {review.strengths && (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-2.5 text-xs">
          <p className="font-medium text-emerald-700 dark:text-emerald-300">优势</p>
          <p className="mt-1 text-muted-foreground">{review.strengths}</p>
        </div>
      )}
      {review.weaknesses && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs">
          <p className="font-medium text-amber-700 dark:text-amber-300">不足</p>
          <p className="mt-1 text-muted-foreground">{review.weaknesses}</p>
        </div>
      )}
      {review.suggestions && (
        <div className="rounded-md border bg-muted/50 p-2.5 text-xs">
          <p className="font-medium">建议</p>
          <p className="mt-1 text-muted-foreground">{review.suggestions}</p>
        </div>
      )}
    </div>
  );
}

export function LiveArtifact({ artifacts, review }: { artifacts?: ArtifactOut[]; review?: ReviewOut | null }) {
  const items = artifacts ?? [];
  const defaultTab = items[0]?.id ?? "review";

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          LiveArtifact
        </p>
        <p className="mt-0.5 text-[10px] text-muted-foreground">
          {items.length} artifact{items.length === 1 ? "" : "s"} ready
        </p>
      </div>

      <Tabs defaultValue={defaultTab} className="flex-1 flex flex-col">
        <div className="border-b px-2">
          <TabsList className="h-9 bg-transparent p-0">
            {items.map((a) => {
              const Icon = ICON_FOR[a.kind] || FileText;
              return (
                <TabsTrigger
                  key={a.id}
                  value={a.id}
                  className="h-9 gap-1.5 rounded-none border-b-2 border-transparent px-3 text-xs data-[state=active]:border-primary data-[state=active]:bg-transparent"
                >
                  <Icon className="h-3 w-3" />
                  {a.title.length > 18 ? a.title.slice(0, 18) + "..." : a.title}
                </TabsTrigger>
              );
            })}
            {review && (
              <TabsTrigger
                value="review"
                className="h-9 gap-1.5 rounded-none border-b-2 border-transparent px-3 text-xs data-[state=active]:border-primary data-[state=active]:bg-transparent"
              >
                <CheckCircle2 className="h-3 w-3" />
                智能评审
              </TabsTrigger>
            )}
          </TabsList>
        </div>

        <ScrollArea className="flex-1">
          {items.map((a) => (
            <TabsContent key={a.id} value={a.id} className="m-0">
              <div className="flex items-center justify-end border-b px-2 py-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => downloadArtifact(a)}
                >
                  <Download className="h-3 w-3" />
                  .{a.kind === "mermaid" ? "mmd" : "md"}
                </Button>
              </div>
              <RenderArtifact a={a} />
            </TabsContent>
          ))}
          {review && (
            <TabsContent value="review" className="m-0">
              <ReviewPanel review={review} />
            </TabsContent>
          )}
        </ScrollArea>
      </Tabs>
    </div>
  );
}
