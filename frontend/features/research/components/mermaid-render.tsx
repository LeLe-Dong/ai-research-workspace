"use client";
import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

let mermaidInitialized = false;
function initMermaid() {
  if (mermaidInitialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "default",
    securityLevel: "loose",
    themeVariables: {
      primaryColor: "#f4f4f5",
      primaryTextColor: "#18181b",
      primaryBorderColor: "#d4d4d8",
      lineColor: "#71717a",
      fontSize: "13px",
    },
  });
  mermaidInitialized = true;
}

export function MermaidRender({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    initMermaid();
    const id = `mmd-${Math.random().toString(36).slice(2)}`;
    mermaid
      .render(id, code)
      .then(({ svg }) => setSvg(svg))
      .catch((e) => setErr(e.message || "渲染失败"));
  }, [code]);

  if (err) return <pre className="text-xs text-destructive">{err}</pre>;
  return <div ref={ref} dangerouslySetInnerHTML={{ __html: svg }} />;
}
