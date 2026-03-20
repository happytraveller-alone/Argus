import { Loader2 } from "lucide-react";

export function DataTableLoadingState({
  label = "加载中...",
}: {
  label?: string;
}) {
  return (
    <div className="flex min-h-32 items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>{label}</span>
    </div>
  );
}
