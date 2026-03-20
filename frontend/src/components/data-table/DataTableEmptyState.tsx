import type { ReactNode } from "react";

export function DataTableEmptyState({
  title = "暂无数据",
  description,
}: {
  title?: ReactNode;
  description?: ReactNode;
}) {
  return (
    <div className="flex min-h-32 flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="text-sm font-semibold text-foreground">{title}</div>
      {description ? (
        <div className="max-w-lg text-sm text-muted-foreground">{description}</div>
      ) : null}
    </div>
  );
}
