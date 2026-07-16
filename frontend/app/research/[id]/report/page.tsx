"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ReportView, ReportError } from "@/features/research/components/report-view";
import { useReport } from "@/features/research/hooks-report";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const { data, isLoading, error } = useReport(params.id);

  if (error) {
    return (
      <div className="container max-w-none px-6 py-6">
        <Button variant="ghost" asChild className="mb-4 -ml-2">
          <Link href={`/research/${params.id}`}>
            <ArrowLeft className="h-3.5 w-3.5" /> Back to research
          </Link>
        </Button>
        <ReportError message={(error as Error).message} />
      </div>
    );
  }

  return (
    <div className="container max-w-none px-6 py-6">
      <Button variant="ghost" asChild className="mb-4 -ml-2">
        <Link href={`/research/${params.id}`}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back to research
        </Link>
      </Button>
      {isLoading || !data ? (
        <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          加载报告中...
        </div>
      ) : (
        <ReportView report={data} />
      )}
    </div>
  );
}
