import { HistoryList } from "@/features/history/components/history-list";

export default function 历史Page() {
  return (
    <div className="container max-w-none px-6 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">历史</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Versioned runs of research projects. MVP shows one row per research;
          v1.3 will add diff / rollback / fork.
        </p>
      </div>
      <HistoryList />
    </div>
  );
}
