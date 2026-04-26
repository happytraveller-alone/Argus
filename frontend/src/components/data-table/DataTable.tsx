import * as React from "react";
import type { RowData } from "@tanstack/react-table";
import {
  type ColumnDef,
  flexRender,
  functionalUpdate,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/shared/utils/utils";
import {
  tanstackFacetFilter,
  tanstackNumberRangeFilter,
  tanstackTextIncludesFilter,
} from "./filterFns";
import { DataTableColumnHeader } from "./DataTableColumnHeader";
import { DataTableEmptyState } from "./DataTableEmptyState";
import { DataTableLoadingState } from "./DataTableLoadingState";
import { DataTablePagination } from "./DataTablePagination";
import { DataTableScrollContainer } from "./DataTableScrollContainer";
import { DataTableSelectionBar } from "./DataTableSelectionBar";
import { DataTableSummaryBar } from "./DataTableSummaryBar";
import { DataTableToolbar } from "./DataTableToolbar";
import { resolveDataTableFilterPlacement } from "./filterPlacement";
import {
  applyDataTableStateUpdate,
  createDefaultDataTableState,
  resolveDataTableState,
} from "./queryState";
import { DATA_TABLE_DENSITY_CELL_CLASS } from "./tableTheme";
import type {
  AppColumnDef,
  DataTableFilterValue,
  DataTableProps,
  DataTableQueryState,
} from "./types";

type AppColumnWithChildren<TData extends RowData> = AppColumnDef<
  TData,
  unknown
> & {
  columns?: AppColumnDef<TData, unknown>[];
};

function resolveFilterFn(column: ColumnDef<any>) {
  const variant = column.meta?.filterVariant;
  if (variant === "select" || variant === "multi-select" || variant === "boolean") {
    return tanstackFacetFilter;
  }
  if (variant === "number-range") {
    return tanstackNumberRangeFilter;
  }
  if (variant === "text") {
    return tanstackTextIncludesFilter;
  }
  return column.filterFn;
}

function resolvePixelSize(value?: string | number) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function buildColumnWithDefaults<TData extends RowData>(
  column: AppColumnDef<TData, unknown>,
): ColumnDef<TData, unknown> {
  const childColumns = (column as AppColumnWithChildren<TData>).columns;
  return {
    ...column,
    ...(childColumns
      ? {
          columns: childColumns.map((childColumn) =>
            buildColumnWithDefaults(childColumn),
          ),
        }
      : {}),
    filterFn: resolveFilterFn(column),
    size: resolvePixelSize(column.meta?.width) ?? column.size,
    minSize: resolvePixelSize(column.meta?.minWidth) ?? column.minSize,
    enableResizing: column.meta?.enableResizing ?? column.enableResizing,
  } as ColumnDef<TData, unknown>;
}

function buildColumnsWithDefaults<TData extends RowData>(
  columns: AppColumnDef<TData, unknown>[],
  enableRowSelection: boolean,
): ColumnDef<TData, unknown>[] {
  const withDefaults = columns.map((column) => buildColumnWithDefaults(column));

  if (!enableRowSelection) {
    return withDefaults;
  }

  const selectionColumn: ColumnDef<TData, unknown> = {
    id: "__select__",
    enableSorting: false,
    enableHiding: false,
    header: ({ table }) => (
      <Checkbox
        aria-label="全选当前页"
        checked={table.getIsAllPageRowsSelected()}
        onCheckedChange={(checked) => table.toggleAllPageRowsSelected(Boolean(checked))}
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        aria-label={`选择第 ${row.index + 1} 行`}
        checked={row.getIsSelected()}
        onCheckedChange={(checked) => row.toggleSelected(Boolean(checked))}
      />
    ),
    meta: {
      label: "选择",
      align: "center",
      hideable: false,
      width: 52,
    },
  };

  return [selectionColumn, ...withDefaults];
}

function renderSummary<TData extends RowData>(
  summary: DataTableProps<TData>["summary"],
  context: {
    table: ReturnType<typeof useReactTable<TData>>;
    rows: TData[];
    filteredCount: number;
    totalCount: number;
  },
) {
  if (!summary) return null;
  if (typeof summary === "function") {
    return summary(context);
  }
  return summary;
}

export function DataTable<TData extends RowData>({
  data,
  columns,
  mode = "local",
  state,
  defaultState,
  resetState,
  onStateChange,
  loading = false,
  error,
  emptyState,
  toolbar,
  selection,
  summary,
  pagination,
  className,
  tableClassName,
  containerClassName,
  tableContainerClassName,
  enableColumnResizing = false,
  getRowId,
}: DataTableProps<TData>) {
  const initialState = React.useMemo(
    () => createDefaultDataTableState(defaultState),
    [defaultState],
  );
  const [internalState, setInternalState] = React.useState<DataTableQueryState>(initialState);
  const resolvedResetState = React.useMemo(
    () => resolveDataTableState(initialState, resetState),
    [initialState, resetState],
  );

  const resolvedState = resolveDataTableState(
    internalState,
    state ? createDefaultDataTableState(state) : undefined,
  );

  const updateState = React.useCallback(
    (updater: ((old: DataTableQueryState) => DataTableQueryState) | DataTableQueryState) => {
      const nextState = applyDataTableStateUpdate(
        resolvedState,
        functionalUpdate(updater as any, resolvedState),
      );
      if (mode === "local" || !state) {
        setInternalState(nextState);
      }
      onStateChange?.(nextState);
    },
    [mode, onStateChange, resolvedState, state],
  );

  const resolvedColumns = React.useMemo(
    () => buildColumnsWithDefaults(columns, Boolean(selection?.enableRowSelection)),
    [columns, selection?.enableRowSelection],
  );
  const paginationConfig = pagination === false ? undefined : pagination;

  const isManualPagination =
    mode === "manual" || Boolean(paginationConfig?.manual);
  const remoteTotalCount = isManualPagination
    ? Math.max(Number(paginationConfig?.totalCount ?? data.length), 0)
    : null;

  const table = useReactTable({
    data,
    columns: resolvedColumns,
    state: {
      globalFilter: resolvedState.globalFilter,
      columnFilters: resolvedState.columnFilters,
      sorting: resolvedState.sorting,
      pagination: resolvedState.pagination,
      columnVisibility: resolvedState.columnVisibility,
      columnSizing: resolvedState.columnSizing,
      rowSelection: resolvedState.rowSelection,
    },
    columnResizeMode: "onChange",
    manualPagination: isManualPagination,
    manualFiltering: isManualPagination,
    manualSorting: isManualPagination,
    rowCount: remoteTotalCount ?? undefined,
    enableRowSelection: selection?.enableRowSelection,
    enableColumnResizing,
    getRowId,
    onGlobalFilterChange: (updater) =>
      updateState((old) => ({
        ...old,
        globalFilter: functionalUpdate(updater, old.globalFilter),
        pagination: { ...old.pagination, pageIndex: 0 },
      })),
    onColumnFiltersChange: (updater) =>
      updateState((old) => ({
        ...old,
        columnFilters: functionalUpdate(updater, old.columnFilters),
        pagination: { ...old.pagination, pageIndex: 0 },
        rowSelection: {},
      })),
    onSortingChange: (updater) =>
      updateState((old) => ({
        ...old,
        sorting: functionalUpdate(updater, old.sorting).slice(0, 1),
      })),
    onPaginationChange: (updater) =>
      updateState((old) => ({
        ...old,
        pagination: functionalUpdate(updater, old.pagination),
        rowSelection: isManualPagination ? {} : old.rowSelection,
      })),
    onColumnVisibilityChange: (updater) =>
      updateState((old) => ({
        ...old,
        columnVisibility: functionalUpdate(updater, old.columnVisibility),
      })),
    onColumnSizingChange: (updater) =>
      updateState((old) => ({
        ...old,
        columnSizing: functionalUpdate(updater, old.columnSizing),
      })),
    onRowSelectionChange: (updater) =>
      updateState((old) => ({
        ...old,
        rowSelection: functionalUpdate(updater, old.rowSelection),
      })),
    globalFilterFn: tanstackTextIncludesFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const filteredCount = remoteTotalCount ?? table.getFilteredRowModel().rows.length;
  const totalCount = remoteTotalCount ?? table.getCoreRowModel().rows.length;
  const visibleRows =
    pagination === false || pagination?.enabled === false
      ? table.getPrePaginationRowModel().rows
      : table.getRowModel().rows;
  const summaryContext = {
    table,
    rows: visibleRows.map((row) => row.original),
    filteredCount,
    totalCount,
  };
  const bodyColSpan = table.getVisibleLeafColumns().length;

  return (
    <div className={cn("overflow-hidden rounded-sm border border-border", className)}>
      <DataTableSummaryBar>{renderSummary(summary, summaryContext)}</DataTableSummaryBar>
      <DataTableToolbar
        table={table}
        toolbar={toolbar}
        state={resolvedState}
        resetState={resolvedResetState}
        onReset={updateState}
        onDensityChange={(density) =>
          updateState((old) => ({
            ...old,
            density,
          }))
        }
      />
      <DataTableSelectionBar
        table={table}
        selection={selection}
        filteredCount={filteredCount}
      />
      <DataTableScrollContainer className={containerClassName}>
        <Table
          className={cn(enableColumnResizing && "table-fixed", tableClassName)}
          containerClassName={tableContainerClassName}
          style={enableColumnResizing ? { width: table.getTotalSize() } : undefined}
        >
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const meta = header.column.columnDef.meta;
                  const fallbackLabel =
                    typeof header.column.columnDef.header === "string"
                      ? header.column.columnDef.header
                      : String(meta?.label || header.column.id);
                  const filterPlacement = resolveDataTableFilterPlacement(meta);
                  const shouldRenderPlainHeader =
                    Boolean(meta?.plainHeader) &&
                    typeof header.column.columnDef.header === "string" &&
                    header.subHeaders.length === 0 &&
                    filterPlacement !== "header";
                  const shouldRenderPlainSortableHeader =
                    shouldRenderPlainHeader &&
                    header.column.getCanSort();
                  const columnWidth = enableColumnResizing
                    ? header.getSize()
                    : meta?.width;
                  const canResizeColumn =
                    enableColumnResizing &&
                    header.subHeaders.length === 0 &&
                    header.column.getCanResize();
                  return (
                    <TableHead
                      key={header.id}
                      colSpan={header.colSpan > 1 ? header.colSpan : undefined}
                      data-align={meta?.align}
                      data-sticky={meta?.sticky}
                      onClick={
                        shouldRenderPlainSortableHeader
                          ? () =>
                              header.column.toggleSorting(
                                header.column.getIsSorted() === "asc",
                              )
                          : undefined
                      }
                      className={cn(
                        "relative",
                        "bg-muted/40",
                        shouldRenderPlainSortableHeader &&
                          "cursor-pointer select-none",
                        meta?.align === "center" && "text-center",
                        meta?.align === "right" && "text-right",
                        meta?.headerClassName,
                      )}
                      style={{
                        width: columnWidth,
                        minWidth: meta?.minWidth,
                      }}
                    >
                      {header.isPlaceholder
                        ? null
                        : typeof header.column.columnDef.header === "string"
                          ? header.subHeaders.length > 0
                            ? String(fallbackLabel)
                            : shouldRenderPlainHeader
                              ? String(fallbackLabel)
                            : (
                                <DataTableColumnHeader
                                  column={header.column as any}
                                  title={String(fallbackLabel)}
                                  defaultFilterValue={
                                    resolvedResetState.columnFilters.find(
                                      (filter) => filter.id === header.column.id,
                                    )?.value as DataTableFilterValue
                                  }
                                />
                              )
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      {canResizeColumn ? (
                        <button
                          type="button"
                          aria-label={`调整${fallbackLabel}列宽`}
                          data-data-table-column-resizer="true"
                          data-resizing={
                            header.column.getIsResizing() ? "true" : undefined
                          }
                          className={cn(
                            "absolute right-0 top-0 h-full w-2 cursor-col-resize touch-none select-none border-r border-transparent transition-colors",
                            "hover:border-primary/50 hover:bg-primary/20",
                            header.column.getIsResizing() &&
                              "border-primary/70 bg-primary/30",
                          )}
                          onClick={(event) => event.stopPropagation()}
                          onDoubleClick={(event) => {
                            event.stopPropagation();
                            header.column.resetSize();
                          }}
                          onMouseDown={(event) => {
                            event.stopPropagation();
                            header.getResizeHandler()(event);
                          }}
                          onTouchStart={(event) => {
                            event.stopPropagation();
                            header.getResizeHandler()(event);
                          }}
                        />
                      ) : null}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={bodyColSpan}>
                  <DataTableLoadingState />
                </TableCell>
              </TableRow>
            ) : error ? (
              <TableRow>
                <TableCell colSpan={bodyColSpan}>
                  <DataTableEmptyState title="加载失败" description={error} />
                </TableCell>
              </TableRow>
            ) : visibleRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={bodyColSpan}>
                  <DataTableEmptyState
                    title={emptyState?.title || "暂无数据"}
                    description={emptyState?.description}
                  />
                </TableCell>
              </TableRow>
            ) : (
              visibleRows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() ? "selected" : undefined}>
                  {row.getVisibleCells().map((cell) => {
                    const meta = cell.column.columnDef.meta;
                    const columnWidth = enableColumnResizing
                      ? cell.column.getSize()
                      : meta?.width;
                    return (
                      <TableCell
                        key={cell.id}
                        data-align={meta?.align}
                        data-sticky={meta?.sticky}
                        className={cn(
                          DATA_TABLE_DENSITY_CELL_CLASS[resolvedState.density],
                          meta?.align === "center" && "text-center",
                          meta?.align === "right" && "text-right",
                          meta?.cellClassName,
                        )}
                        style={{
                          width: columnWidth,
                          minWidth: meta?.minWidth,
                        }}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </DataTableScrollContainer>
      <DataTablePagination
        table={table}
        config={pagination}
        filteredCount={filteredCount}
        totalCount={totalCount}
      />
    </div>
  );
}
