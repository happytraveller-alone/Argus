import * as React from "react";

import { cn } from "@/shared/utils/utils";

type InputProps = React.ComponentProps<"input"> & {
  startIcon?: React.ReactNode;
  wrapperClassName?: string;
  startIconClassName?: string;
};

function Input({
  className,
  type,
  startIcon,
  wrapperClassName,
  startIconClassName,
  ...props
}: InputProps) {
  const inputNode = (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground font-mono font-medium flex h-11 w-full min-w-0 rounded-sm border border-input bg-background px-4 py-2.5 text-base shadow-none transition-[border-color,box-shadow] outline-none file:inline-flex file:h-9 file:border-0 file:bg-transparent file:text-base file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "focus:border-primary/70 focus:bg-muted/20",
        "aria-invalid:border-secondary",
        startIcon && "!pl-11",
        className
      )}
      {...props}
    />
  );

  if (!startIcon) {
    return inputNode;
  }

  return (
    <div className={cn("relative", wrapperClassName)}>
      <span
        className={cn(
          "pointer-events-none absolute inset-y-0 left-0 flex w-11 items-center justify-center text-muted-foreground",
          startIconClassName
        )}
      >
        {startIcon}
      </span>
      {inputNode}
    </div>
  );
}

export { Input };
