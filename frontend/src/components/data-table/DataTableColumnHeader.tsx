import type { Column } from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  ListFilter,
  X,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/shared/utils/utils";
import { resolveDataTableFilterPlacement } from "./filterPlacement";
import type { DataTableFilterValue, DataTableNumberRangeValue } from "./types";

function SortIcon({ state }: { state: false | "asc" | "desc" }) {
  if (state === "asc") return <ArrowUp className="h-4 w-4" />;
  if (state === "desc") return <ArrowDown className="h-4 w-4" />;
  return <ArrowUpDown className="h-4 w-4 opacity-60" />;
}

function isFilterActive(value: DataTableFilterValue) {
  if (value === undefined || value === null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") {
    const range = value as DataTableNumberRangeValue;
    return range.min !== undefined || range.max !== undefined;
  }
  return true;
}

function normalizeNumberInput(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function HeaderFilterTrigger({
  title,
  active,
  weakHighlight,
}: {
  title: string;
  active: boolean;
  weakHighlight: boolean;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-label={`筛选${title}`}
      data-filter-active={active ? "true" : undefined}
      data-data-table-filter-trigger="true"
      className={cn(
        "h-8 w-8 shrink-0 rounded-l-none border-l border-border/70 px-0 !whitespace-nowrap bg-transparent text-foreground/60 hover:bg-muted/55 hover:text-foreground",
        active && "font-bold text-primary hover:bg-primary/10 hover:text-primary",
        !active &&
          weakHighlight &&
          "font-semibold text-sky-300 hover:bg-sky-500/10 hover:text-sky-200",
      )}
      onClick={(event) => event.stopPropagation()}
      onPointerDown={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <ListFilter className="h-4 w-4" />
    </Button>
  );
}

function HeaderTextFilter<TData, TValue>({
  column,
  title,
  currentValue,
  filterActive,
  showWeakHighlight,
}: {
  column: Column<TData, TValue>;
  title: string;
  currentValue: DataTableFilterValue;
  filterActive: boolean;
  showWeakHighlight: boolean;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <HeaderFilterTrigger
          title={title}
          active={filterActive}
          weakHighlight={showWeakHighlight}
        />
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-72 space-y-3 p-3"
        portal={false}
      >
        <div className="space-y-1.5">
          <Label className="font-mono text-xs font-bold uppercase text-muted-foreground">
            {title}
          </Label>
          <Input
            value={String(currentValue ?? "")}
            onChange={(event) => column.setFilterValue(event.target.value)}
            placeholder={
              column.columnDef.meta?.filterPlaceholder || `筛选${title}`
            }
            className="cyber-input h-9"
          />
        </div>
        {filterActive ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-full justify-start gap-2 text-xs"
            onClick={() => column.setFilterValue(undefined)}
          >
            <X className="h-3.5 w-3.5" />
            清除筛选
          </Button>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function HeaderNumberRangeFilter<TData, TValue>({
  column,
  title,
  currentValue,
  filterActive,
  showWeakHighlight,
}: {
  column: Column<TData, TValue>;
  title: string;
  currentValue: DataTableFilterValue;
  filterActive: boolean;
  showWeakHighlight: boolean;
}) {
  const rangeValue =
    currentValue &&
    typeof currentValue === "object" &&
    !Array.isArray(currentValue)
      ? (currentValue as DataTableNumberRangeValue)
      : {};

  return (
    <Popover>
      <PopoverTrigger asChild>
        <HeaderFilterTrigger
          title={title}
          active={filterActive}
          weakHighlight={showWeakHighlight}
        />
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-72 space-y-3 p-3"
        portal={false}
      >
        <div className="space-y-2">
          <Label className="font-mono text-xs font-bold uppercase text-muted-foreground">
            {title}
          </Label>
          <div className="grid grid-cols-2 gap-2">
            <Input
              inputMode="numeric"
              value={String(rangeValue.min ?? "")}
              onChange={(event) =>
                column.setFilterValue({
                  ...rangeValue,
                  min: normalizeNumberInput(event.target.value),
                })
              }
              placeholder="最小"
              className="cyber-input h-9"
            />
            <Input
              inputMode="numeric"
              value={String(rangeValue.max ?? "")}
              onChange={(event) =>
                column.setFilterValue({
                  ...rangeValue,
                  max: normalizeNumberInput(event.target.value),
                })
              }
              placeholder="最大"
              className="cyber-input h-9"
            />
          </div>
        </div>
        {filterActive ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-full justify-start gap-2 text-xs"
            onClick={() => column.setFilterValue(undefined)}
          >
            <X className="h-3.5 w-3.5" />
            清除筛选
          </Button>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function HeaderOptionFilter<TData, TValue>({
  column,
  title,
  currentValue,
  filterActive,
  showWeakHighlight,
}: {
  column: Column<TData, TValue>;
  title: string;
  currentValue: DataTableFilterValue;
  filterActive: boolean;
  showWeakHighlight: boolean;
}) {
  const filterVariant = column.columnDef.meta?.filterVariant;
  const filterOptions = column.columnDef.meta?.filterOptions || [];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <HeaderFilterTrigger
          title={title}
          active={filterActive}
          weakHighlight={showWeakHighlight}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[180px]">
        <DropdownMenuLabel>{title}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {filterVariant === "multi-select" ? (
          <>
            {filterOptions.map((option) => {
              const selectedValues = Array.isArray(currentValue)
                ? currentValue
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
              currentValue === undefined ||
              currentValue === null ||
              currentValue === ""
                ? "__all__"
                : String(currentValue)
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
  );
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
  const currentFilterValue = column.getFilterValue() as DataTableFilterValue;
  const filterActive = isFilterActive(currentFilterValue);
  const showWeakHighlight = filterActive || defaultFilterValue !== undefined;
  const canFilterInHeader =
    filterPlacement === "header" && Boolean(filterVariant);
  const canSort = column.getCanSort();
  const sortState = column.getIsSorted();

  if (!canSort && !canFilterInHeader) {
    return (
      <span
        className={cn(
          "inline-flex items-center font-mono text-xs font-medium uppercase tracking-[0.16em] text-foreground/80",
          headerContentClassName,
          className,
        )}
      >
        {title}
      </span>
    );
  }

  return (
    <div
      data-data-table-header-control="true"
      className={cn(
        "inline-flex h-8 items-center gap-0 overflow-hidden whitespace-nowrap rounded-sm border border-border/70 bg-background/45 shadow-sm transition-colors hover:border-border",
        className,
      )}
    >
      {canSort ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn(
            "h-8 gap-1 rounded-r-none bg-transparent px-2 font-mono text-xs uppercase tracking-[0.16em] !whitespace-nowrap hover:bg-muted/55 hover:text-foreground",
            sortState
              ? "font-bold text-primary"
              : "font-medium text-foreground/80",
            headerContentClassName,
          )}
          onClick={() => column.toggleSorting(sortState === "asc")}
        >
          <span className="whitespace-nowrap">{title}</span>
          <SortIcon state={sortState} />
        </Button>
      ) : (
        <span
          className={cn(
            "inline-flex h-8 items-center px-2 font-mono text-xs font-medium uppercase tracking-[0.16em] text-foreground/80",
            headerContentClassName,
          )}
        >
          {title}
        </span>
      )}
      {canFilterInHeader && filterVariant === "text" ? (
        <HeaderTextFilter
          column={column}
          title={title}
          currentValue={currentFilterValue}
          filterActive={filterActive}
          showWeakHighlight={showWeakHighlight}
        />
      ) : null}
      {canFilterInHeader && filterVariant === "number-range" ? (
        <HeaderNumberRangeFilter
          column={column}
          title={title}
          currentValue={currentFilterValue}
          filterActive={filterActive}
          showWeakHighlight={showWeakHighlight}
        />
      ) : null}
      {canFilterInHeader &&
      (filterVariant === "select" ||
        filterVariant === "multi-select" ||
        filterVariant === "boolean") ? (
        <HeaderOptionFilter
          column={column}
          title={title}
          currentValue={currentFilterValue}
          filterActive={filterActive}
          showWeakHighlight={showWeakHighlight}
        />
      ) : null}
    </div>
  );
}
