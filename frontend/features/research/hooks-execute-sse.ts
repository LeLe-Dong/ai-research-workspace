"use client";
/**
 * useResearchStream — subscribes to backend SSE endpoint for real-time updates.

 * Replaces 2-3s polling with actual server-pushed events:
 * - timeline: any new AgentEvent (immediate)
 * - artifacts: when a new artifact is emitted
 * - task: when task status changes
 * - status: when research status changes

 * Falls back to polling if EventSource fails (network, browser support).
 */
import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

const API_BASE = (typeof window !== "undefined"
  ? `${window.location.protocol}//${window.location.hostname}:8003`
  : "http://127.0.0.1:8003");

interface StreamEvent {
  type: "timeline" | "task" | "artifact" | "status" | "heartbeat" | "end" | "error";
  [k: string]: unknown;
}

export function useResearchStream(researchId: string | null, enabled: boolean = true) {
  const qc = useQueryClient();
  const lastSeqRef = useRef(0);

  useEffect(() => {
    if (!researchId || !enabled) return;

    let es: EventSource | null = null;
    let pollFallback: ReturnType<typeof setInterval> | null = null;
    let stopped = false;

    const start = () => {
      if (stopped) return;
      try {
        es = new EventSource(`${API_BASE}/api/v1/researches/${researchId}/stream`);

        es.onmessage = (event) => {
          try {
            const data: StreamEvent = JSON.parse(event.data);
            if (data.type === "end" || data.type === "error") {
              // Force a final fetch and close
              qc.invalidateQueries({ queryKey: ["research", researchId] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "tasks"] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "timeline"] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "artifacts"] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "review"] });
              es?.close();
              return;
            }
            if (data.type === "timeline") {
              qc.invalidateQueries({ queryKey: ["research", researchId, "timeline"] });
            } else if (data.type === "task") {
              qc.invalidateQueries({ queryKey: ["research", researchId, "tasks"] });
            } else if (data.type === "artifact") {
              qc.invalidateQueries({ queryKey: ["research", researchId, "artifacts"] });
            } else if (data.type === "status") {
              qc.invalidateQueries({ queryKey: ["research", researchId] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "review"] });
            }
          } catch (e) {
            // Ignore parse errors; the next event might be valid
          }
        };

        es.onerror = () => {
          // EventSource auto-reconnects, but if it errors 3 times in a row we fall back to polling
          es?.close();
          es = null;
          if (pollFallback === null) {
            pollFallback = setInterval(() => {
              qc.invalidateQueries({ queryKey: ["research", researchId] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "tasks"] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "timeline"] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "artifacts"] });
              qc.invalidateQueries({ queryKey: ["research", researchId, "review"] });
            }, 3000);
          }
        };
      } catch (e) {
        // Browser doesn't support EventSource; poll as fallback
        if (pollFallback === null) {
          pollFallback = setInterval(() => {
            qc.invalidateQueries({ queryKey: ["research", researchId] });
            qc.invalidateQueries({ queryKey: ["research", researchId, "tasks"] });
            qc.invalidateQueries({ queryKey: ["research", researchId, "timeline"] });
            qc.invalidateQueries({ queryKey: ["research", researchId, "artifacts"] });
            qc.invalidateQueries({ queryKey: ["research", researchId, "review"] });
          }, 3000);
        }
      }
    };

    start();

    return () => {
      stopped = true;
      es?.close();
      if (pollFallback) clearInterval(pollFallback);
    };
  }, [researchId, enabled, qc]);
}
