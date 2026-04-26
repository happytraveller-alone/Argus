import type { Column } from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  ListFilter,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/shared/utils/utils";
import { resolveDataTableFilterPlacement } from "./filterPlacement";
import type { DataTableFilterValue } from "./types";

function SortIcon({ state }: { state: false | "asc" | "desc" }) {
  if (state === "asc") return <ArrowUp className="h-4 w-4" />;
  if (state === "desc") return <ArrowDown className="h-4 w-4" />;
  return <ArrowUpDown className="h-4 w-4 opacity-60" />;
}

export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
  defaultFilterValue,
}: {
  column: Column<TData, TValue>;
  title: string;
  className?: string;
  defaultFilterValue?: DataTableFilterValue;
}) {
  const meta = column.columnDef.meta;
  const headerContentClassName = meta?.headerContentClassName;
  const filterPlacement = resolveDataTableFilterPlacement(meta);
  const filterVariant = meta?.filterVariant;
  const filterOptions = meta?.filterOptions || [];
  const canFilterInHeader =
    filterPlacement === "header" &&
    (filterVariant === "select" ||
      filterVariant === "multi-select" ||
      filterVariant === "boolean") &&
    filterOptions.length > 0;
  const currentFilterValue = column.getFilterValue() as DataTableFilterValue;
  const filterActive =
    currentFilterValue !== undefined &&
    currentFilterValue !== null &&
    currentFilterValue !== "" &&
    (!Array.isArray(currentFilterValue) || currentFilterValue.length > 0);
  const showWeakHighlight = filterActive || defaultFilterValue !== undefined;

  if (!column.getCanSort() && !canFilterInHeader) {
    return (
      <span
        className={cn("inline-flex items-center", headerContentClassName, className)}
      >
        {title}
      </span>
    );
  }

  return (
    <div className={cn("inline-flex items-center gap-1 whitespace-nowrap", className)}>
      {column.getCanSort() ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn(
            "h-8 -ml-2 gap-1 px-2 font-mono text-xs uppercase tracking-[0.16em] text-foreground/80 !whitespace-nowrap hover:bg-muted/70",
            headerContentClassName,
          )}
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          <span className="whitespace-nowrap">{title}</span>
          <SortIcon state={column.getIsSorted()} />
        </Button>
      ) : (
        <span
          className={cn(
            "font-mono text-xs uppercase tracking-[0.16em] text-foreground/80",
            headerContentClassName,
          )}
        >
          {title}
        </span>
      )}
      {canFilterInHeader ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={`筛选${title}`}
              data-filter-active={filterActive ? "true" : undefined}
              className={cn(
                "h-8 w-8 shrink-0 px-0 !whitespace-nowrap text-foreground/60 hover:bg-muted/70 hover:text-foreground",
                showWeakHighlight &&
                  "border border-sky-500/30 bg-sky-500/10 text-sky-300 hover:bg-sky-500/15 hover:text-sky-200",
              )}
            >
              <ListFilter className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-[180px]">
            <DropdownMenuLabel>{title}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {filterVariant === "multi-select" ? (
              <>
                {filterOptions.map((option) => {
                  const selectedValues = Array.isArray(currentFilterValue)
                    ? currentFilterValue
                    : [];
                  return (
                    <DropdownMenuCheckboxItem
                      key={option.value}
                      checked={selectedValues.includes(option.value)}
                      onCheckedChange={(checked) => {
                        const next = new Set(selectedValues);
                        if (checked) {
                          next.add(option.value);
                        } else {
                          next.delete(option.value);
                        }
                        column.setFilterValue(Array.from(next));
                      }}
                    >
                      {option.label}
                    </DropdownMenuCheckboxItem>
                  );
                })}
              </>
            ) : (
              <DropdownMenuRadioGroup
                value={
                  currentFilterValue === undefined ||
                  currentFilterValue === null ||
                  currentFilterValue === ""
                    ? "__all__"
                    : String(currentFilterValue)
                }
                onValueChange={(value) =>
                  column.setFilterValue(value === "__all__" ? undefined : value)
                }
              >
                <DropdownMenuRadioItem value="__all__">全部</DropdownMenuRadioItem>
                {filterOptions.map((option) => (
                  <DropdownMenuRadioItem key={option.value} value={option.value}>
                    {option.label}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            )}
            {filterActive ? (
              <>
                <DropdownMenuSeparator />
                <div className="px-2 py-1.5 text-[11px] uppercase tracking-[0.12em] text-sky-300">
                  <Check className="mr-1 inline h-3 w-3" />
                  已筛选
                </div>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  );
}
