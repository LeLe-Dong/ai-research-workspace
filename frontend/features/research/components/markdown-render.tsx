"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, Info, AlertTriangle, CheckCircle, Lightbulb } from "lucide-react";
import { useState, ReactNode } from "react";

import { Button } from "@/components/ui/button";

/**
 * Render research-report markdown with publication-grade typography.
 * Designed for long Chinese reports (8000+ chars, 12 sections).
 */
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
        className="absolute right-2 top-2 z-10 h-7 w-7 bg-background/80 backdrop-blur"
        onClick={onCopy}
        aria-label="复制 Markdown"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>

      <article className="report-prose">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          urlTransform={(value) => {
            // react-markdown default blocks data: URLs — allow them for inline SVG placeholders
            if (value && value.startsWith("data:")) return value;
            if (value && /^(https?|ircs?|mailto|xmpp):/i.test(value)) return value;
            if (value && !value.includes(":")) return value; // relative URL
            // Block javascript:, vbscript:, etc.
            return value || "";
          }}
          components={{
            // H1: report title — only used as a top-level
            h1: ({ children, id }) => (
              <h1 id={id} className="report-h1">
                {children}
              </h1>
            ),
            // H2: section heading with anchor + numbered badge
            h2: ({ children, id }) => {
              const childText = typeof children === "string" ? children : String(children || "");
              const numMatch = childText.match(/^(\d+)[.、]\s*/);
              let num = "•";
              let rest = childText;
              if (numMatch) {
                num = numMatch[1];
                rest = childText.slice(numMatch[0].length);
              }
              return (
                <h2 id={id} className="report-h2">
                  <span className="report-h2-badge">{num}</span>
                  <span className="report-h2-text">{rest}</span>
                </h2>
              );
            },
            // H3: subsection
            h3: ({ children, id }) => (
              <h3 id={id} className="report-h3">
                {children}
              </h3>
            ),
            // Paragraphs
            p: ({ children }) => <p className="report-p">{children}</p>,
            // Unordered list
            ul: ({ children }) => <ul className="report-ul">{children}</ul>,
            // Ordered list
            ol: ({ children }) => <ol className="report-ol">{children}</ol>,
            // List item
            li: ({ children }) => <li className="report-li">{children}</li>,
            // Strong
            strong: ({ children }) => <strong className="report-strong">{children}</strong>,
            // Tables
            table: ({ children }) => (
              <div className="report-table-wrap">
                <table className="report-table">{children}</table>
              </div>
            ),
            thead: ({ children }) => <thead className="report-thead">{children}</thead>,
            tbody: ({ children }) => <tbody className="report-tbody">{children}</tbody>,
            tr: ({ children }) => <tr className="report-tr">{children}</tr>,
            th: ({ children }) => <th className="report-th">{children}</th>,
            td: ({ children }) => <td className="report-td">{children}</td>,
            // Images
            img: ({ src, alt }) => (
              <span className="report-img-wrap">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={src}
                  alt={alt || ""}
                  className="report-img"
                  loading="lazy"
                  // Only apply crossOrigin to real http(s) URLs — data: URIs don't
                  // support CORS and would fail with crossOrigin="anonymous".
                  crossOrigin={typeof src === "string" && src.startsWith("http") ? "anonymous" : undefined}
                  referrerPolicy="no-referrer"
                  onError={(e) => {
                    const target = e.currentTarget;
                    if (!target.dataset.fallback) {
                      target.dataset.fallback = "1";
                      target.classList.add("report-img-broken");
                      target.alt = (target.alt || "") + " (图片加载失败)";
                    }
                  }}
                />
                {alt && <span className="report-img-caption">{alt}</span>}
              </span>
            ),
            // Horizontal rule
            hr: () => <hr className="report-hr" />,
            // Code (inline + block)
            code: ({ children, className }) => {
              const isBlock = className?.includes("language-");
              return isBlock ? (
                <pre className="report-pre"><code className={className}>{children}</code></pre>
              ) : (
                <code className="report-code">{children}</code>
              );
            },
            pre: ({ children }) => <>{children}</>, // handled by code
            // Blockquote
            blockquote: ({ children }) => {
              const text = String(children);
              const match = text.match(/^\s*\[(NOTE|WARNING|SUCCESS|TIP)\]\s*/);
              if (match) {
                const inner = text.replace(/^\s*\[(NOTE|WARNING|SUCCESS|TIP)\]\s*/, "");
                return <Callout type={match[1]}>{inner}</Callout>;
              }
              return <blockquote className="report-blockquote">{children}</blockquote>;
            },
            // Links
            a: ({ children, href }) => (
              <a href={href} className="report-a" target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </article>
    </div>
  );
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
    <div className={"my-5 flex gap-3 rounded-md border p-3.5 " + c.className}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1 text-sm leading-relaxed">{children}</div>
    </div>
  );
}
