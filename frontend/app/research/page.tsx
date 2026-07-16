import { ResearchList } from "@/features/research/components/research-list";

export default function ResearchPage() {
  return (
    <div className="container max-w-none px-6 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">研究</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理与查看本工作区的所有研究项目。
        </p>
      </div>
      <ResearchList />
    </div>
  );
}
