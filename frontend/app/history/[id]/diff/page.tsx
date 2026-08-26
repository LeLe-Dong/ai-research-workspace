"use client";
import { useSearchParams, useParams } from "next/navigation";
import { useDiff, useVersions } from "@/features/history/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, ArrowRight, FileText, GitCompare, Loader2, AlertTriangle } from "lucide-react";
import Link from "next/link";

export default function DiffPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const researchId = params.id as string;
  const v1 = parseInt(searchParams.get("v1") || "0", 10);
  const v2 = parseInt(searchParams.get("v2") || "0", 10);

  const { data: versions } = useVersions(researchId);
  const { data: diff, isLoading } = useDiff(researchId, v1 || null, v2 || null);

  if (!v1 || !v2) {
    return (
      <div className="container max-w-none px-6 py-6">
        <p className="text-sm text-muted-foreground">缺少版本参数</p>
        <Button asChild className="mt-4">
          <Link href={`/history/${researchId}`}>返回历史</Link>
        </Button>
      </div>
    );
  }

  const v1Info = versions?.find((v) => v.version === v1);
  const v2Info = versions?.find((v) => v.version === v2);

  return (
    <div className="container max-w-none px-6 py-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">版本对比</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            v{v1} vs v{v2}
            {v1Info && <span className="ml-2 text-xs">({v1Info.title})</span>}
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href={`/history/${researchId}`}>
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
            返回历史
          </Link>
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">加载对比数据...</span>
        </div>
      ) : !diff ? (
        <Card>
          <CardContent className="py-12 text-center">
            <AlertTriangle className="mx-auto h-8 w-8 text-amber-500" />
            <p className="mt-2 text-sm text-muted-foreground">无法加载对比数据</p>
          </CardContent>
        </Card>
      ) : !diff.changed ? (
        <Card>
          <CardContent className="py-12 text-center">
            <GitCompare className="mx-auto h-8 w-8 text-muted-foreground" />
            <p className="mt-2 text-sm text-muted-foreground">两个版本之间没有差异</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* Version info cards */}
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Badge variant="outline" className="h-4">v{v1}</Badge>
                  {v1Info?.status === "completed" ? "已完成" : v1Info?.status || "未知"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-xs text-muted-foreground">
                {v1Info?.created_at && <p>创建于 {new Date(v1Info.created_at).toLocaleString()}</p>}
                {v1Info?.commit_message && <p>备注: {v1Info.commit_message}</p>}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Badge variant="outline" className="h-4">v{v2}</Badge>
                  {v2Info?.status === "completed" ? "已完成" : v2Info?.status || "未知"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-xs text-muted-foreground">
                {v2Info?.created_at && <p>创建于 {new Date(v2Info.created_at).toLocaleString()}</p>}
                {v2Info?.commit_message && <p>备注: {v2Info.commit_message}</p>}
              </CardContent>
            </Card>
          </div>

          {/* Field diffs */}
          {diff.field_diffs.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <FileText className="h-3.5 w-3.5 text-blue-500" />
                  字段差异 ({diff.field_diffs.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {diff.field_diffs.map((fd, i) => (
                    <div key={i} className="rounded border p-3">
                      <p className="mb-2 text-xs font-semibold">{fd.field}</p>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="rounded bg-red-500/5 p-2">
                          <p className="mb-1 text-[10px] font-medium text-red-600">v{v1}</p>
                          <p className="whitespace-pre-wrap text-xs">{fd.v1 || "(空)"}</p>
                        </div>
                        <div className="rounded bg-emerald-500/5 p-2">
                          <p className="mb-1 text-[10px] font-medium text-emerald-600">v{v2}</p>
                          <p className="whitespace-pre-wrap text-xs">{fd.v2 || "(空)"}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Report diffs */}
          {diff.report_diffs.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <FileText className="h-3.5 w-3.5 text-indigo-500" />
                  报告差异
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {diff.report_diffs.map((rd, i) => (
                    <div key={i} className="flex items-center justify-between rounded border px-3 py-2">
                      <span className="text-xs">{rd.field}</span>
                      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                        <span>v{v1}: {rd.v1_len} 字符</span>
                        <ArrowRight className="h-3 w-3" />
                        <span>v{v2}: {rd.v2_len} 字符</span>
                        <Badge variant={rd.changed ? "warning" : "secondary"} className="h-4 text-[9px]">
                          {rd.changed ? "已变更" : "无变化"}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
