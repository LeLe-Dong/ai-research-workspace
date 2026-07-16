"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, Info, AlertTriangle, CheckCircle, Lightbulb } from "lucide-react";
import { useState, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/**
 * Pre-process markdown to convert custom callout syntax:
 *   > [!NOTE] text     → blue callout
 *   > [!WARNING] text   → amber callout
 *   > [!SUCCESS] text   → emerald callout
 *   > [!TIP] text       → purple callout
 */
function preprocessCallouts(content: string): string {
  return content
    .replace(/^> \[!NOTE\][\s\S]*?(?=\n(?!>\[!)|^> )/gm, (m) => m.replace(/^> \[!NOTE\]\s*/, "> [!NOTE] "))
    .replace(/^> \[!WARNING\][\s\S]*?(?=\n(?!>\[!)|^> )/gm, (m) => m.replace(/^> \[!WARNING\]\s*/, "> [!WARNING] "));
}

function Callout({ type, children }: { type: string; children: ReactNode }) {
  const config: Record<string, { icon: any; className: string; label: string }> = {
    NOTE: { icon: Info, className: "border-blue-500/30 bg-blue-500/5 text-blue-700 dark:text-blue-300", label: "提示" },
    WARNING: { icon: AlertTriangle, className: "border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300", label: "注意" },
    SUCCESS: { icon: CheckCircle, className: "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300", label: "成功" },
    TIP: { icon: Lightbulb, className: "border-purple-500/30 bg-purple-500/5 text-purple-700 dark:text-purple-300", label: "建议" },
  };
  const c = config[type] || config.NOTE;
  const Icon = c.icon;
  return (
    <div className={"my-4 flex gap-3 rounded-md border p-3 " + c.className}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1 text-sm leading-relaxed">{children}</div>
    </div>
  );
}

export function MarkdownRender({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-1 top-1 z-10 h-7 w-7"
        onClick={onCopy}
        aria-label="复制 Markdown"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
      <div className="prose prose-sm dark:prose-invert max-w-none p-5
        prose-headings:font-semibold prose-headings:tracking-tight
        prose-h1:text-2xl prose-h1:border-b prose-h1:pb-3 prose-h1:mb-4
        prose-h2:text-lg prose-h2:mt-7 prose-h2:mb-3 prose-h2:pb-2 prose-h2:border-b
        prose-h3:text-base prose-h3:mt-5 prose-h3:mb-2
        prose-p:my-2.5 prose-p:leading-relaxed
        prose-ul:my-3 prose-ul:space-y-1
        prose-ol:my-3
        prose-li:my-1
        prose-strong:font-semibold prose-strong:text-foreground
        prose-table:text-xs prose-table:my-4
        prose-th:bg-muted/50 prose-th:font-semibold
        prose-td:border prose-td:px-3 prose-td:py-2
        prose-blockquote:border-l-4 prose-blockquote:border-primary/50
        prose-blockquote:bg-muted/30 prose-blockquote:py-2 prose-blockquote:px-4
        prose-blockquote:not-italic prose-blockquote:text-muted-foreground
        prose-hr:my-6 prose-hr:border-border
        prose-code:before:content-none prose-code:after:content-none
      ">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Custom h1 with icon
            h1: ({ children }) => (
              <h1 className="flex items-center gap-2">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">📄</span>
                {children}
              </h1>
            ),
            // Custom h2 with section number badge
            h2: ({ children }) => (
              <h2 className="flex items-center gap-2">
                <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-muted text-[10px] font-bold text-muted-foreground">
                  {typeof children === "string" ? children.toString().slice(0, 1) : "•"}
                </span>
                {children}
              </h2>
            ),
            // Callout blockquote - if it starts with [!NOTE] etc
            blockquote: ({ children }) => {
              const text = String(children);
              const match = text.match(/^\s*\[!(NOTE|WARNING|SUCCESS|TIP)\]\s*/);
              if (match) {
                const inner = text.replace(/^\s*\[!(NOTE|WARNING|SUCCESS|TIP)\]\s*/, "");
                return (
                  <Callout type={match[1]}>
                    {inner}
                  </Callout>
                );
              }
              return <blockquote>{children}</blockquote>;
            },
            // Tables: add hover row
            table: ({ children }) => (
              <div className="my-4 overflow-x-auto rounded-md border">
                <table className="w-full">{children}</table>
              </div>
            ),
            // First td of each row gets bold for dimension labels
            th: ({ children }) => <th className="text-left">{children}</th>,
            // Strong inside first cell
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
