"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ResearchList } from "@/features/research/components/research-list";
import { Skeleton } from "@/components/ui/skeleton";

function ResearchListWithSearch() {
  const searchParams = useSearchParams();
  const q = searchParams.get("q") || undefined;
  return <ResearchList searchQuery={q} />;
}

export default function ResearchPage() {
  return (
    <div className="container max-w-none px-6 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">研究</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理与查看本工作区的所有研究项目。
        </p>
      </div>
      <Suspense fallback={
        <div className="space-y-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      }>
        <ResearchListWithSearch />
      </Suspense>
    </div>
  );
}
