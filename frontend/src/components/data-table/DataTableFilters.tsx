import type { Table } from "@tanstack/react-table";
import { ListFilter } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/shared/utils/utils";
import type { DataTableToolbarFilterConfig } from "./types";

function FilterContainer({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-[160px] flex-1">
      <Label className="font-mono text-xs font-bold uppercase text-muted-foreground">
        {label}
      </Label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

export function DataTableFilters<TData>({
  table,
  filters,
  className,
}: {
  table: Table<TData>;
  filters: DataTableToolbarFilterConfig[];
  className?: string;
}) {
  if (filters.length === 0) return null;

  return (
    <div className={cn("flex flex-1 flex-wrap items-end gap-3", className)}>
      {filters.map((filter) => {
        const column = table.getColumn(filter.columnId);
        if (!column) return null;
        const variant = filter.variant ?? "select";
        const currentValue = column.getFilterValue();

        if (variant === "text") {
          return (
            <FilterContainer key={filter.columnId} label={filter.label}>
              <Input
                value={String(currentValue ?? "")}
                onChange={(event) => column.setFilterValue(event.target.value)}
                placeholder={filter.placeholder || `筛选${filter.label}`}
                className="cyber-input h-10"
              />
            </FilterContainer>
          );
        }

        if (variant === "multi-select") {
          const selectedValues = Array.isArray(currentValue) ? currentValue : [];
          return (
            <FilterContainer key={filter.columnId} label={filter.label}>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    className="cyber-input h-10 w-full justify-between px-3"
                  >
                    <span className="truncate">
                      {selectedValues.length > 0
                        ? `${selectedValues.length} 项已选`
                        : filter.placeholder || `选择${filter.label}`}
                    </span>
                    <ListFilter className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="min-w-[200px]">
                  <DropdownMenuLabel>{filter.label}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {(filter.options || []).map((option) => (
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
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </FilterContainer>
          );
        }

        if (variant === "number-range") {
          const rangeValue =
            currentValue && typeof currentValue === "object" ? currentValue : {};
          return (
            <FilterContainer key={filter.columnId} label={filter.label}>
              <div className="flex items-center gap-2">
                <Input
                  inputMode="numeric"
                  value={String((rangeValue as any).min ?? "")}
                  onChange={(event) => {
                    const nextMin = event.target.value ? Number(event.target.value) : undefined;
                    column.setFilterValue({
                      ...(rangeValue as object),
                      min: nextMin,
                    });
                  }}
                  placeholder="最小"
                  className="cyber-input h-10"
                />
                <Input
                  inputMode="numeric"
                  value={String((rangeValue as any).max ?? "")}
                  onChange={(event) => {
                    const nextMax = event.target.value ? Number(event.target.value) : undefined;
                    column.setFilterValue({
                      ...(rangeValue as object),
                      max: nextMax,
                    });
                  }}
                  placeholder="最大"
                  className="cyber-input h-10"
                />
              </div>
            </FilterContainer>
          );
        }

        return (
          <FilterContainer key={filter.columnId} label={filter.label}>
            <Select
              value={
                currentValue === undefined || currentValue === null || currentValue === ""
                  ? "all"
                  : String(currentValue)
              }
              onValueChange={(value) =>
                column.setFilterValue(value === "all" ? undefined : value)
              }
            >
              <SelectTrigger className="cyber-input h-10">
                <SelectValue placeholder={filter.placeholder || `选择${filter.label}`} />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                <SelectItem value="all">全部</SelectItem>
                {(filter.options || []).map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterContainer>
        );
      })}
    </div>
  );
}
