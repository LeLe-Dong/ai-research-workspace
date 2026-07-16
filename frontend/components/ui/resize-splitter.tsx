"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface ResizeSplitterProps {
  /** Current size in pixels */
  size: number;
  /** Callback when size changes during drag */
  onResize: (size: number) => void;
  /** Direction: "horizontal" = vertical splitter line, "vertical" = horizontal splitter line */
  direction: "horizontal" | "vertical";
  /** Min size in pixels */
  min?: number;
  /** Max size as percentage (0-1) of parent */
  maxPercent?: number;
  /** Save key (e.g. "console-height") - persists to localStorage */
  storageKey?: string;
  /** Aria label for a11y */
  ariaLabel?: string;
}

/**
 * Drag-to-resize splitter line. Use between two resizable areas.
 * Persists size to localStorage if storageKey provided.
 */
export function ResizeSplitter({
  size: controlledSize,
  onResize,
  direction,
  min = 100,
  maxPercent = 0.8,
  storageKey,
  ariaLabel = "Resize",
}: ResizeSplitterProps) {
  const [isDragging, setIsDragging] = useState(false);
  const parentRef = useRef<HTMLDivElement | null>(null);
  const startPos = useRef(0);
  const startSize = useRef(0);

  // Calculate max size based on parent
  const getMaxSize = useCallback(() => {
    if (!parentRef.current) return 1000;
    const parent = parentRef.current;
    return direction === "horizontal"
      ? parent.clientWidth * maxPercent
      : parent.clientHeight * maxPercent;
  }, [direction, maxPercent]);

  const handleStart = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      setIsDragging(true);
      startPos.current = direction === "horizontal" ? e.clientX : e.clientY;
      startSize.current = controlledSize;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [controlledSize, direction]
  );

  const handleMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging) return;
      const current = direction === "horizontal" ? e.clientX : e.clientY;
      const delta = current - startPos.current;
      const newSize = Math.max(min, Math.min(getMaxSize(), startSize.current + delta));
      onResize(newSize);
    },
    [isDragging, direction, onResize, min, getMaxSize]
  );

  const handleEnd = useCallback(
    (e: React.PointerEvent) => {
      if (isDragging) {
        setIsDragging(false);
        try {
          (e.target as HTMLElement).releasePointerCapture(e.pointerId);
        } catch {
          // ignore
        }
        // Save to localStorage
        if (storageKey) {
          try {
            localStorage.setItem(`airw:resize:${storageKey}`, String(controlledSize));
          } catch {
            // ignore
          }
        }
      }
    },
    [isDragging, storageKey, controlledSize]
  );

  // Restore from localStorage on mount
  useEffect(() => {
    if (storageKey) {
      try {
        const saved = localStorage.getItem(`airw:resize:${storageKey}`);
        if (saved) {
          const parsed = Number(saved);
          if (parsed >= min) {
            onResize(parsed);
          }
        }
      } catch {
        // ignore
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={parentRef}
      role="separator"
      aria-orientation={direction === "horizontal" ? "vertical" : "horizontal"}
      aria-label={ariaLabel}
      aria-valuenow={Math.round(controlledSize)}
      onPointerDown={handleStart}
      onPointerMove={handleMove}
      onPointerUp={handleEnd}
      onPointerCancel={handleEnd}
      className={cn(
        "relative flex shrink-0 items-center justify-center bg-border transition-colors",
        direction === "horizontal"
          ? "w-1 cursor-col-resize hover:bg-primary/50"
          : "h-1 cursor-row-resize hover:bg-primary/50",
        isDragging && "bg-primary"
      )}
    >
      {/* Visual grip indicator */}
      <div
        className={cn(
          "absolute rounded-full bg-muted-foreground/40 transition-opacity",
          direction === "horizontal"
            ? "h-8 w-0.5"
            : "h-0.5 w-8",
          isDragging ? "opacity-0" : "opacity-0 hover:opacity-100"
        )}
      />
    </div>
  );
}
