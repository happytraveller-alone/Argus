import * as React from "react";

import { cn } from "@/shared/utils/utils";

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "border-input placeholder:text-muted-foreground focus-visible:border-primary/70 focus-visible:bg-muted/20 aria-invalid:border-destructive flex field-sizing-content min-h-28 w-full rounded-sm border bg-background px-4 py-3 text-base font-mono font-medium leading-relaxed shadow-none transition-[color,background-color,border-color] outline-none disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}
