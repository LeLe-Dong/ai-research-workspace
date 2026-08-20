"use client";
/**
 * PrefetchLink — same API as next/link but also fires a React Query
 * prefetch when the user hovers / focuses / touches. Designed for the
 * "查看运行详情" / "查看报告" buttons: by the time the user actually
 * clicks, /research/{id}/execute and its 4 datasets are already cached.
 */
import Link, { type LinkProps } from "next/link";
import { useCallback, type ReactNode } from "react";

interface PrefetchLinkProps extends LinkProps {
  /** Called on mouseenter / focus / touchstart. Should be idempotent. */
  onPrefetch?: () => void;
  children: ReactNode;
}

export function PrefetchLink({ onPrefetch, children, ...rest }: PrefetchLinkProps) {
  // Trigger as soon as the pointer is on the link. React Query dedupes by
  // queryKey so calling twice is harmless; if the user moves on without
  // clicking, the in-flight requests get cancelled automatically.
  const trigger = useCallback(() => {
    if (onPrefetch) onPrefetch();
  }, [onPrefetch]);

  return (
    <Link
      {...rest}
      onMouseEnter={trigger}
      onFocus={trigger}
      onTouchStart={trigger}
    >
      {children}
    </Link>
  );
}