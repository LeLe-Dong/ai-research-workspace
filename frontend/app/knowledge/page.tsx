import { KnowledgeManager } from "@/features/knowledge/components/knowledge-manager";
import { KnowledgeList } from "@/features/knowledge/components/kb-list";
import { BookOpen, Sparkles, Library } from "lucide-react";

export default function KnowledgePage() {
  return (
    <div className="container max-w-none px-6 py-6 space-y-6">
      {/* Section 1: Personalization */}
      <div>
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <BookOpen className="h-6 w-6 text-blue-500" />
              知识库与个性化
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              上传历史预研报告 → 抽取章节结构与写作风格 → 在新建研究时启用「使用我的风格」。
            </p>
          </div>
        </div>
        <KnowledgeManager />
      </div>

      {/* Section 2: Past research archive */}
      <div className="border-t pt-6">
        <h2 className="mb-4 flex items-center gap-2 text-xl font-semibold tracking-tight">
          <Library className="h-5 w-5 text-emerald-500" />
          历史研究归档
        </h2>
        <KnowledgeList />
      </div>
    </div>
  );
}