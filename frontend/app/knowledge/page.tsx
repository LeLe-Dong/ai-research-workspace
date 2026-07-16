import { KnowledgeList } from "@/features/knowledge/components/kb-list";

export default function KnowledgePage() {
  return (
    <div className="container max-w-none px-6 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">知识库</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          所有已完成的研究，可搜索、可复用。
        </p>
      </div>
      <KnowledgeList />
    </div>
  );
}
