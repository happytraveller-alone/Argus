import { cn } from "@/shared/utils/utils";

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("rounded-sm bg-transparent", className)}
      {...props}
    />
  );
}

export { Skeleton };
