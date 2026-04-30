import type { PropsWithChildren } from "react";
import { cn } from "@/shared/utils/utils";

export function DataTableSummaryBar({
  children,
  className,
}: PropsWithChildren<{ className?: string }>) {
  if (!children) return null;
  return (
    <div className={cn("border-b border-border/60 px-4 py-3", className)}>
      {children}
    </div>
  );
}
