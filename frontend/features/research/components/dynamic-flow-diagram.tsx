"use client";
import { useMemo } from "react";
import { Loader2 } from "lucide-react";
import { MermaidRender } from "./mermaid-render";
import type { TaskNode } from "@/lib/types";

const PHASE_ORDER = ["requirement", "research", "comparison", "evaluation", "report"] as const;
const PHASE_LABELS: Record<string, string> = {
  requirement: "需求分析",
  research: "信息收集",
  comparison: "对比分析",
  evaluation: "可行性评估",
  report: "报告撰写",
};

const PHASE_COLOR: Record<string, string> = {
  requirement: "#1e40af",
  research: "#4338ca",
  comparison: "#7c3aed",
  evaluation: "#b45309",
  report: "#059669",
};

/**
 * Dynamic research flow diagram that highlights current phase.
 * Pure function: derives mermaid code from task data.
 */
export function DynamicFlowDiagram({ tasks, researchStatus }: { tasks?: TaskNode[]; researchStatus?: string }) {
  const mermaidCode = useMemo(() => {
    if (!tasks || tasks.length === 0) {
      // Fallback: static diagram
      return `graph TD
        A[研究目标] --> B[需求分析]
        B --> C[信息收集]
        C --> D[对比分析]
        D --> E[可行性评估]
        E --> F[推荐方案]
        F --> G[最终报告]
        style A fill:#1e40af,stroke:#1e3a8a,color:#fff
        style G fill:#059669,stroke:#047857,color:#fff
      `;
    }

    // Group tasks by phase and compute per-phase status
    const byPhase: Record<string, TaskNode[]> = {};
    for (const t of tasks) {
      (byPhase[t.phase] ??= []).push(t);
    }
    const phaseStatus: Record<string, "pending" | "running" | "done"> = {};
    for (const [phase, items] of Object.entries(byPhase)) {
      if (items.every(t => t.status === "done")) phaseStatus[phase] = "done";
      else if (items.some(t => t.status === "running" || t.status === "done")) phaseStatus[phase] = "running";
      else phaseStatus[phase] = "pending";
    }

    // Build mermaid code
    const lines: string[] = ["graph TD"];
    const seen = new Set<string>();
    const nodeId = (phase: string) => phase.replace(/\W/g, "_");

    // Edges
    const orderedPhases = PHASE_ORDER.filter(p => byPhase[p] || PHASE_LABELS[p]);
    orderedPhases.forEach((p, i) => {
      if (i > 0) {
        const prev = orderedPhases[i - 1];
        lines.push(`${nodeId(prev)} --> ${nodeId(p)}`);
      }
    });
    // Add edge to final report
    if (researchStatus === "completed") {
      const last = orderedPhases[orderedPhases.length - 1];
      lines.push(`${nodeId(last)} --> FINAL[最终报告]`);
    }

    // Node definitions with status styles
    for (const phase of orderedPhases) {
      const status = phaseStatus[phase] || "pending";
      const color = PHASE_COLOR[phase] || "#6b7280";
      const label = `${PHASE_LABELS[phase] || phase}\n(${byPhase[phase]?.filter(t => t.status === "done").length || 0}/${byPhase[phase]?.length || 0})`;
      lines.push(`${nodeId(phase)}["${label}"]`);
      seen.add(phase);
    }
    if (researchStatus === "completed") {
      lines.push(`FINAL["最终报告 ✓"]`);
    }

    // Style each node based on its status
    for (const phase of orderedPhases) {
      const status = phaseStatus[phase];
      const color = PHASE_COLOR[phase] || "#6b7280";
      const id = nodeId(phase);
      if (status === "done") {
        // Completed - full color, light fill
        lines.push(`style ${id} fill:${color},stroke:${color},color:#fff,font-weight:bold`);
      } else if (status === "running") {
        // In progress - bold border, animated
        lines.push(`style ${id} fill:#fff,stroke:${color},stroke-width:3px,color:${color},font-weight:bold`);
        lines.push(`classDef ${id}Anim fill:#fff,stroke:${color},stroke-width:3px,color:${color}`);
        // The "running" class is a hint - actual animation via CSS on the SVG element
      } else {
        // Pending - faded
        lines.push(`style ${id} fill:#f4f4f5,stroke:#a1a1aa,color:#71717a,stroke-dasharray:5,5`);
      }
    }
    if (researchStatus === "completed") {
      lines.push(`style FINAL fill:#059669,stroke:#047857,color:#fff,font-weight:bold`);
    }

    return lines.join("\n");
  }, [tasks, researchStatus]);

  return (
    <div className="relative">
      <MermaidRender code={mermaidCode} />
      {researchStatus === "running" && (
        <div className="absolute right-2 top-2 flex items-center gap-1.5 rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-300">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inset-0 animate-ping rounded-full bg-blue-500 opacity-75"></span>
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-blue-500"></span>
          </span>
          实时更新中
        </div>
      )}
    </div>
  );
}
