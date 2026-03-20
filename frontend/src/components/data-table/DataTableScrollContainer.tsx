import type { PropsWithChildren } from "react";
import { cn } from "@/shared/utils/utils";

export function DataTableScrollContainer({
  children,
  className,
}: PropsWithChildren<{ className?: string }>) {
  return (
    <div className={cn("relative w-full overflow-x-auto", className)}>
      {children}
    </div>
  );
}
