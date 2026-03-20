import type { Table } from "@tanstack/react-table";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DataTableColumnVisibility } from "./DataTableColumnVisibility";
import { DataTableDensityToggle } from "./DataTableDensityToggle";
import { DataTableFilters } from "./DataTableFilters";
import { resolveDataTableFilterPlacement } from "./filterPlacement";
import { hasActiveDataTableFilters, resetDataTableFilters } from "./queryState";
import type { DataTableDensity, DataTableQueryState, DataTableToolbarConfig } from "./types";

export function DataTableToolbar<TData>({
  table,
  toolbar,
  state,
  resetState,
  onReset,
  onDensityChange,
}: {
  table: Table<TData>;
  toolbar?: false | DataTableToolbarConfig<TData>;
  state: DataTableQueryState;
  resetState?: Partial<DataTableQueryState>;
  onReset: (nextState: DataTableQueryState) => void;
  onDensityChange: (nextDensity: DataTableDensity) => void;
}) {
  if (toolbar === false) return null;

  const filterConfigs =
    toolbar?.filters ??
    table
      .getAllLeafColumns()
      .filter(
        (column) => resolveDataTableFilterPlacement(column.columnDef.meta) === "toolbar",
      )
      .map((column) => ({
        columnId: column.id,
        label: String(column.columnDef.meta?.label || column.id),
        variant: column.columnDef.meta?.filterVariant,
        options: column.columnDef.meta?.filterOptions,
        placeholder: column.columnDef.meta?.filterPlaceholder,
      }));

  return (
    <div className="space-y-3 border-b border-border/60 px-4 py-4">
      <div className="flex flex-wrap items-end gap-3">
        {toolbar?.showGlobalSearch === false ? null : (
          <div className="relative w-full max-w-sm shrink-0">
            <div className="relative">
              {/* <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /> */}
              <Input
                value={state.globalFilter}
                onChange={(event) => table.setGlobalFilter(event.target.value)}
                placeholder={toolbar?.searchPlaceholder || "搜索..."}
                className="cyber-input h-10 pl-11 pr-4"
              />
            </div>
          </div>
        )}

        <DataTableFilters table={table} filters={filterConfigs} />

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {toolbar?.leadingActions}
          {toolbar?.showDensityToggle === false ? null : (
            <DataTableDensityToggle density={state.density} onChange={onDensityChange} />
          )}
          {toolbar?.showColumnVisibility === false ? null : (
            <DataTableColumnVisibility table={table} />
          )}
          {toolbar?.showReset === false ? null : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="cyber-btn-outline h-9 px-3"
              onClick={() => onReset(resetDataTableFilters(state, resetState))}
              disabled={!hasActiveDataTableFilters(state, resetState)}
            >
              重置
            </Button>
          )}
          {toolbar?.trailingActions}
        </div>
      </div>
      {toolbar?.summarySlot ? <div>{toolbar.summarySlot}</div> : null}
    </div>
  );
}
