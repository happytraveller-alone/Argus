import * as React from "react";
import type { RowData } from "@tanstack/react-table";
import {
  type Cell,
  type Column,
  type ColumnDef,
  flexRender,
  functionalUpdate,
  getCoreRowModel,
  getFacetedRowModel,
  getFacetedUniqueValues,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type Header,
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

const AUTO_COLUMN_MIN_WIDTH_PX = 64;
const AUTO_COLUMN_MAX_WIDTH_PX = 520;
const AUTO_COLUMN_CHARACTER_WIDTH_PX = 8;
const AUTO_COLUMN_HORIZONTAL_PADDING_PX = 24;

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

function resolveStringSize(value?: string | number) {
  return typeof value === "string" && value.trim().length > 0
    ? value
    : undefined;
}

function buildColumnWithDefaults<TData extends RowData>(
  column: AppColumnDef<TData, unknown>,
): ColumnDef<TData, unknown> {
  const childColumns = (column as AppColumnWithChildren<TData>).columns;
  const hasAccessor = Boolean(
    (column as any).accessorFn || (column as any).accessorKey,
  );
  const needsAutoFilter =
    hasAccessor &&
    !column.meta?.filterVariant &&
    !column.meta?.plainHeader &&
    column.enableColumnFilter !== false;
  const resolvedMeta = needsAutoFilter
    ? { ...column.meta, filterVariant: "multi-select" as const }
    : column.meta;
  const resolvedColumn = needsAutoFilter
    ? { ...column, meta: resolvedMeta }
    : column;
  return {
    ...resolvedColumn,
    ...(childColumns
      ? {
          columns: childColumns.map((childColumn) =>
            buildColumnWithDefaults(childColumn),
          ),
        }
      : {}),
    filterFn: resolveFilterFn(resolvedColumn),
    size: resolvePixelSize(resolvedMeta?.width) ?? column.size,
    minSize: resolvePixelSize(resolvedMeta?.minWidth) ?? column.minSize,
    enableResizing: resolvedMeta?.enableResizing ?? column.enableResizing,
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

function isWideCharacter(character: string) {
  return /[\u1100-\u115f\u2329\u232a\u2e80-\ua4cf\uac00-\ud7a3\uf900-\ufaff\ufe10-\ufe19\ufe30-\ufe6f\uff00-\uff60\uffe0-\uffe6]/u.test(
    character,
  );
}

function countTextUnits(text: string) {
  return Array.from(text).reduce(
    (total, character) => total + (isWideCharacter(character) ? 2 : 1),
    0,
  );
}

function countRenderableTextUnits(value: unknown): number {
  if (value === null || value === undefined || value === false) {
    return 0;
  }

  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "bigint" ||
    typeof value === "boolean"
  ) {
    return countTextUnits(String(value));
  }

  if (Array.isArray(value)) {
    return value.reduce(
      (total, child) => total + countRenderableTextUnits(child),
      0,
    );
  }

  if (React.isValidElement(value)) {
    return countRenderableTextUnits(
      (value as React.ReactElement<{ children?: React.ReactNode }>).props
        .children,
    );
  }

  return 0;
}

function clampAutoColumnWidth(width: number) {
  return Math.min(
    Math.max(Math.ceil(width), AUTO_COLUMN_MIN_WIDTH_PX),
    AUTO_COLUMN_MAX_WIDTH_PX,
  );
}

function resolveAutoColumnWidth(
  textUnits: number,
  minWidth?: string | number,
  preferredWidth?: string | number,
  maxWidth?: string | number,
) {
  const calculatedWidth = clampAutoColumnWidth(
    textUnits * AUTO_COLUMN_CHARACTER_WIDTH_PX +
      AUTO_COLUMN_HORIZONTAL_PADDING_PX,
  );
  const numericMinWidth = resolvePixelSize(minWidth);
  const numericPreferredWidth = resolvePixelSize(preferredWidth);
  const numericMaxWidth = resolvePixelSize(maxWidth);
  const lowerBoundedWidth = Math.max(
    calculatedWidth,
    numericMinWidth ?? 0,
    numericPreferredWidth ?? 0,
  );
  return numericMaxWidth
    ? Math.min(lowerBoundedWidth, numericMaxWidth)
    : lowerBoundedWidth;
}

function getColumnHeaderTextUnits<TData extends RowData>(
  header: Header<TData, unknown>,
) {
  const headerContent = header.column.columnDef.header;
  if (typeof headerContent === "string") {
    return countTextUnits(headerContent);
  }
  return countTextUnits(String(header.column.columnDef.meta?.label || header.column.id));
}

function getCellTextUnits<TData extends RowData>(cell: Cell<TData, unknown>) {
  const renderedCell = flexRender(cell.column.columnDef.cell, cell.getContext());
  const renderedTextUnits = countRenderableTextUnits(renderedCell);
  return renderedTextUnits || countRenderableTextUnits(cell.getValue());
}

function getHeaderAutoWidth<TData extends RowData>(
  header: Header<TData, unknown>,
  autoColumnWidths: Record<string, number>,
): number | undefined {
  if (header.subHeaders.length > 0) {
    return header.subHeaders.reduce(
      (total, subHeader) =>
        total + (getHeaderAutoWidth(subHeader, autoColumnWidths) ?? 0),
      0,
    );
  }

  return autoColumnWidths[header.column.id];
}

function getCellAutoWidth<TData extends RowData>(
  cell: Cell<TData, unknown>,
  autoColumnWidths: Record<string, number>,
): number | undefined {
  return autoColumnWidths[cell.column.id];
}

function hasStringColumnSizing(column: Column<any, unknown>) {
  const meta = column.columnDef.meta;
  return Boolean(
    resolveStringSize(meta?.width) ||
      resolveStringSize(meta?.minWidth) ||
      resolveStringSize(meta?.maxWidth),
  );
}

function resolveAutoStyleWidth(
  meta: ColumnDef<any>["meta"],
  autoWidth: number | undefined,
) {
  return resolveStringSize(meta?.width) ?? autoWidth;
}

function resolveAutoStyleMinWidth(
  meta: ColumnDef<any>["meta"],
  width: string | number | undefined,
) {
  return resolveStringSize(meta?.minWidth) ?? width ?? meta?.minWidth;
}

function resolveAutoStyleMaxWidth(meta: ColumnDef<any>["meta"]) {
  return resolveStringSize(meta?.maxWidth) ?? resolvePixelSize(meta?.maxWidth);
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
  renderMode,
  pagination,
  className,
  tableClassName,
  containerClassName,
  tableContainerClassName,
  fillContainerWidth = false,
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
    getFacetedRowModel: getFacetedRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
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
  const autoColumnWidths = React.useMemo(() => {
    if (enableColumnResizing) {
      return {};
    }

    const maxTextUnitsByColumn: Record<string, number> = {};

    table.getHeaderGroups().forEach((headerGroup) => {
      headerGroup.headers.forEach((header) => {
        if (header.isPlaceholder || header.subHeaders.length > 0) {
          return;
        }
        maxTextUnitsByColumn[header.column.id] = Math.max(
          maxTextUnitsByColumn[header.column.id] ?? 0,
          getColumnHeaderTextUnits(header),
        );
      });
    });

    visibleRows.forEach((row) => {
      row.getVisibleCells().forEach((cell) => {
        maxTextUnitsByColumn[cell.column.id] = Math.max(
          maxTextUnitsByColumn[cell.column.id] ?? 0,
          getCellTextUnits(cell),
        );
      });
    });

    return table.getVisibleLeafColumns().reduce<Record<string, number>>(
      (widths, column) => {
        widths[column.id] = resolveAutoColumnWidth(
          maxTextUnitsByColumn[column.id] ?? 0,
          column.columnDef.meta?.minWidth,
          column.columnDef.meta?.width,
          column.columnDef.meta?.maxWidth,
        );
        return widths;
      },
      {},
    );
  }, [enableColumnResizing, table, visibleRows]);
  const hasStringSizedColumns =
    !enableColumnResizing &&
    table.getVisibleLeafColumns().some((column) => hasStringColumnSizing(column));
  const autoTableWidth = enableColumnResizing
    ? undefined
    : hasStringSizedColumns && !fillContainerWidth
      ? undefined
      : table
          .getVisibleLeafColumns()
          .reduce(
            (total, column) => total + (autoColumnWidths[column.id] ?? 0),
            0,
          );
  const summaryContext = {
    table,
    rows: visibleRows.map((row) => row.original),
    filteredCount,
    totalCount,
  };
  const renderModeContext = {
    ...summaryContext,
    rowModels: visibleRows,
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
      {renderMode ? (
        <div className={cn("min-w-0", containerClassName)}>
          {renderMode(renderModeContext)}
        </div>
      ) : (
      <DataTableScrollContainer className={containerClassName}>
        <Table
          className={cn(enableColumnResizing && "table-fixed", tableClassName)}
          containerClassName={tableContainerClassName}
          style={{
            width: enableColumnResizing
              ? table.getTotalSize()
              : fillContainerWidth
                ? "100%"
                : autoTableWidth,
            minWidth:
              !enableColumnResizing && fillContainerWidth
                ? autoTableWidth
                : undefined,
          }}
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
                  const autoColumnWidth = getHeaderAutoWidth(
                    header,
                    autoColumnWidths,
                  );
                  const columnWidth = enableColumnResizing
                    ? header.getSize()
                    : resolveAutoStyleWidth(meta, autoColumnWidth);
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
                      data-no-i18n={meta?.dataNoI18n ? "true" : undefined}
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
                        shouldRenderPlainSortableHeader &&
                          "cursor-pointer select-none",
                        meta?.align === "center" && "text-center",
                        meta?.align === "right" && "text-right",
                        meta?.headerClassName,
                      )}
                      style={{
                        width: columnWidth,
                        minWidth: enableColumnResizing
                          ? meta?.minWidth
                          : resolveAutoStyleMinWidth(meta, columnWidth),
                        maxWidth: enableColumnResizing
                          ? undefined
                          : resolveAutoStyleMaxWidth(meta),
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
                    const autoColumnWidth = getCellAutoWidth(
                      cell,
                      autoColumnWidths,
                    );
                    const columnWidth = enableColumnResizing
                      ? cell.column.getSize()
                      : resolveAutoStyleWidth(meta, autoColumnWidth);
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
                          minWidth: enableColumnResizing
                            ? meta?.minWidth
                            : resolveAutoStyleMinWidth(meta, columnWidth),
                          maxWidth: enableColumnResizing
                            ? undefined
                            : resolveAutoStyleMaxWidth(meta),
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
      )}
      <DataTablePagination
        table={table}
        config={pagination}
        filteredCount={filteredCount}
        totalCount={totalCount}
      />
    </div>
  );
}
