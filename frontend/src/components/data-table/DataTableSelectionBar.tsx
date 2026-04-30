import type { Table } from "@tanstack/react-table";
import type { ReactNode } from "react";
import type { DataTableSelectionConfig } from "./types";

export function DataTableSelectionBar<TData>({
  table,
  selection,
  filteredCount,
}: {
  table: Table<TData>;
  selection?: DataTableSelectionConfig<TData>;
  filteredCount: number;
}) {
  if (!selection?.enableRowSelection) return null;

  const selectedRows = table.getSelectedRowModel().rows.map((row) => row.original);
  const selectedCount = selectedRows.length;
  if (selectedCount === 0 && !selection.actions) return null;

  const context = {
    table,
    selectedRows,
    selectedCount,
    filteredCount,
  };

  const summary =
    selection.summary?.(context) ??
    (`已选择 ${selectedCount} 条，当前筛选结果共 ${filteredCount} 条` as ReactNode);

  return (
    <div className="border-b border-border/60 bg-primary/5 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-mono">{summary}</div>
        {selection.actions ? (
          <div className="flex flex-wrap items-center gap-2">
            {selection.actions(context)}
          </div>
        ) : null}
      </div>
    </div>
  );
}
