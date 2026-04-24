import type { Table } from "@tanstack/react-table";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DATA_TABLE_PAGE_SIZE_OPTIONS,
  type DataTablePaginationConfig,
  type DataTableSummaryContext,
} from "./types";

export function DataTablePagination<TData>({
  table,
  config,
  filteredCount,
  totalCount,
}: {
  table: Table<TData>;
  config?: false | DataTablePaginationConfig<TData>;
  filteredCount: number;
  totalCount: number;
}) {
  if (config === false || config?.enabled === false) return null;

  const pageSizeOptions = config?.pageSizeOptions ?? [...DATA_TABLE_PAGE_SIZE_OPTIONS];
  const pageIndex = table.getState().pagination.pageIndex;
  const pageSize = table.getState().pagination.pageSize;
  const pageCount = Math.max(1, table.getPageCount());
  const context: DataTableSummaryContext<TData> = {
    table,
    rows: table.getRowModel().rows.map((row) => row.original),
    filteredCount,
    totalCount,
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 px-4 py-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>每页显示:</span>
        <Select
          value={String(pageSize)}
          onValueChange={(value) => table.setPageSize(Number(value))}
        >
          <SelectTrigger className="cyber-input h-8 w-[88px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="cyber-dialog border-border">
            {pageSizeOptions.map((option) => (
              <SelectItem key={option} value={String(option)}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="text-sm text-muted-foreground">
        {config?.infoLabel?.(context) ?? `共 ${filteredCount} 条，第 ${pageIndex + 1} / ${pageCount} 页`}
      </div>

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="cyber-btn-outline h-8"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
        >
          <ChevronLeft className="h-4 w-4" />
          上一页
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="cyber-btn-outline h-8"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
        >
          下一页
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
