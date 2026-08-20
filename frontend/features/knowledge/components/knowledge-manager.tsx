"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Upload, FileText, Sparkles, Trash2, ChevronRight, Sparkle, BookOpen, Layers } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { knowledgeApi, type KnowledgeDoc, type KnowledgeStyle } from "../api";

export function KnowledgeManager() {
  const [docs, setDocs] = useState<KnowledgeDoc[] | null>(null);
  const [styles, setStyles] = useState<KnowledgeStyle[] | null>(null);
  const [current, setCurrent] = useState<KnowledgeStyle | null>(null);
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    try {
      const [d, s, c] = await Promise.all([
        knowledgeApi.listDocuments(),
        knowledgeApi.listStyles(),
        knowledgeApi.currentStyle(),
      ]);
      setDocs(d.items);
      setStyles(s.items);
      setCurrent(c.active);
    } catch (err) {
      toast.error("加载失败", { description: (err as Error).message });
    }
  };

  useEffect(() => { refresh(); }, []);

  const onUpload = async (file: File) => {
    setUploading(true);
    try {
      const d = await knowledgeApi.upload(file);
      toast.success("已上传", { description: `${d.filename} · ${d.sections_count} 章节` });
      await refresh();
    } catch (err) {
      toast.error("上传失败", { description: (err as Error).message });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const [extractName, setExtractName] = useState("");
  const [suggestedName, setSuggestedName] = useState("");

  // Auto-suggest a name based on documents
  const suggestName = async () => {
    if (!docs || docs.length === 0) return;
    const first = docs[0];
    const stem = first.filename.replace(/\.[^.]+$/, "").slice(0, 20);
    if (docs.length > 1) setSuggestedName(`${stem}+${docs.length - 1} 篇`);
    else setSuggestedName(stem);
  };

  const onExtract = async () => {
    setExtracting(true);
    try {
      // Pass the user's name OR let backend auto-derive
      const s = await knowledgeApi.extractStyle(extractName.trim() || undefined);
      toast.success("风格已抽取并激活", {
        description: `${s.name} · ${s.dimensions.length} 个维度 · ${s.tone}/${s.length_pref}/${s.quantification}`,
      });
      setExtractName("");
      await refresh();
    } catch (err) {
      toast.error("抽取失败", { description: (err as Error).message });
    } finally {
      setExtracting(false);
    }
  };

  const onDeleteDoc = async (id: string, name: string) => {
    if (!confirm(`删除「${name}」？此操作不可撤销。`)) return;
    try {
      await knowledgeApi.deleteDocument(id);
      toast.success("已删除");
      await refresh();
    } catch (err) {
      toast.error("删除失败", { description: (err as Error).message });
    }
  };

  const onActivate = async (id: string) => {
    try {
      await knowledgeApi.activateStyle(id);
      toast.success("已切换为该风格");
      await refresh();
    } catch (err) {
      toast.error("切换失败", { description: (err as Error).message });
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Upload */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Upload className="h-4 w-4 text-blue-500" />
            上传预研文档
            <Badge variant="outline" className="ml-auto h-5 text-xs">{docs?.length ?? 0}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            上传你过去的预研报告 (.md / .txt)，系统会抽取你的章节结构和写作风格。
            抽取后会作为可选开关注入到后续研究的 prompt 中。
          </p>
          <div className="flex items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".md,.markdown,.txt,.pdf,text/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUpload(f);
              }}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
            >
              <Upload className="mr-1.5 h-3.5 w-3.5" />
              {uploading ? "上传中..." : "选择文件"}
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={extractName || suggestedName}
              onChange={(e) => setExtractName(e.target.value)}
              onFocus={suggestName}
              placeholder={suggestedName || "风格名称（留空自动生成）"}
              className="h-8 flex-1 rounded-md border bg-background px-2 text-xs outline-none focus:ring-1 focus:ring-primary"
              disabled={!docs || docs.length === 0}
            />
            <Button
              type="button"
              variant="default"
              size="sm"
              disabled={extracting || !docs || docs.length === 0}
              onClick={onExtract}
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              {extracting ? "抽取中..." : "抽取风格"}
            </Button>
          </div>
          <div className="max-h-64 space-y-1 overflow-auto">
            {docs === null ? (
              <Skeleton className="h-10 w-full" />
            ) : docs.length === 0 ? (
              <p className="px-2 py-3 text-center text-xs text-muted-foreground">
                暂无文档
              </p>
            ) : (
              docs.map((d) => (
                <div key={d.id} className="group flex items-center gap-2 rounded-md border bg-background/50 px-2 py-1.5">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate text-xs">{d.filename}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {(d.byte_size / 1024).toFixed(1)} KB · {d.sections_count} 章节
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 group-hover:opacity-100"
                    onClick={() => onDeleteDoc(d.id, d.filename)}
                  >
                    <Trash2 className="h-3 w-3 text-destructive" />
                  </Button>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Style preview */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkle className="h-4 w-4 text-amber-500" />
            当前激活风格
            {current && (
              <Badge variant="default" className="ml-auto h-5 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/15">
                <span className="mr-1 h-1.5 w-1.5 rounded-full bg-emerald-500" />
                ACTIVE
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!current ? (
            <div className="rounded-md border border-dashed bg-muted/20 px-3 py-6 text-center text-xs text-muted-foreground">
              尚未抽取风格。上传文档后点击「抽取风格」。
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <Badge variant="outline" className="text-[10px]">{current.tone}</Badge>
                <Badge variant="outline" className="text-[10px]">{current.length_pref}</Badge>
                <Badge variant="outline" className="text-[10px]">{current.quantification}</Badge>
                <span className="ml-auto text-[10px] text-muted-foreground">{current.dimensions.length} 个维度</span>
              </div>
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">研究维度</p>
                <ol className="space-y-0.5 text-xs">
                  {current.dimensions.map((d, i) => (
                    <li key={i} className="flex gap-1.5">
                      <span className="shrink-0 text-muted-foreground tabular-nums">{i + 1}.</span>
                      <span className="truncate">{d}</span>
                    </li>
                  ))}
                </ol>
              </div>
              {current.custom_instructions && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">额外指引</p>
                  <p className="rounded-md border bg-muted/30 px-2 py-1.5 text-xs leading-relaxed text-muted-foreground">
                    {current.custom_instructions}
                  </p>
                </div>
              )}
            </>
          )}
          {styles && styles.length > 1 && (
            <div className="border-t pt-3">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                切换风格 ({styles.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {styles.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => onActivate(s.id)}
                    className={cn(
                      "rounded-md border px-2 py-1 text-[11px] transition-colors",
                      s.is_active
                        ? "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                        : "hover:bg-accent/30"
                    )}
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}