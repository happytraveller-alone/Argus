import type {
  ColumnDef,
  ColumnFiltersState,
  PaginationState,
  RowData,
  RowSelectionState,
  SortingState,
  Table,
} from "@tanstack/react-table";
import type { ReactNode } from "react";

export const DATA_TABLE_PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

export type DataTableDensity = "compact" | "comfortable" | "spacious";
export type DataTableMode = "local" | "controlled" | "manual";
export type DataTableAlign = "left" | "center" | "right";
export type DataTableSticky = "left" | "right";
export type DataTableFilterVariant =
  | "text"
  | "select"
  | "multi-select"
  | "boolean"
  | "number-range";
export type DataTableFilterPlacement = "auto" | "header" | "toolbar" | "none";

export interface DataTableFilterOption {
  label: string;
  value: string;
}

export interface DataTableNumberRangeValue {
  min?: number;
  max?: number;
}

export type DataTableFilterValue =
  | string
  | string[]
  | boolean
  | DataTableNumberRangeValue
  | null
  | undefined;

export interface DataTableColumnMeta<TData = unknown, TValue = unknown> {
  label?: string;
  align?: DataTableAlign;
  minWidth?: string | number;
  width?: string | number;
  sticky?: DataTableSticky;
  hideable?: boolean;
  sortable?: boolean;
  plainHeader?: boolean;
  filterVariant?: DataTableFilterVariant;
  filterPlacement?: DataTableFilterPlacement;
  filterOptions?: DataTableFilterOption[];
  densityClassName?: string;
  mobilePriority?: number;
  headerClassName?: string;
  headerContentClassName?: string;
  cellClassName?: string;
  filterPlaceholder?: string;
  _row?: TData;
  _value?: TValue;
}

export type AppColumnDef<TData, TValue = unknown> = ColumnDef<TData, TValue> & {
  meta?: DataTableColumnMeta<TData, TValue>;
};

declare module "@tanstack/react-table" {
  interface ColumnMeta<TData extends RowData, TValue>
    extends DataTableColumnMeta<TData, TValue> {}
}

export interface DataTableQueryState {
  globalFilter: string;
  columnFilters: ColumnFiltersState;
  sorting: SortingState;
  pagination: PaginationState;
  columnVisibility: Record<string, boolean>;
  rowSelection: RowSelectionState;
  density: DataTableDensity;
}

export interface DataTableToolbarFilterConfig {
  columnId: string;
  label: string;
  variant?: DataTableFilterVariant;
  placeholder?: string;
  options?: DataTableFilterOption[];
}

export interface DataTableToolbarConfig<TData> {
  showGlobalSearch?: boolean;
  searchPlaceholder?: string;
  filters?: DataTableToolbarFilterConfig[];
  showColumnVisibility?: boolean;
  showDensityToggle?: boolean;
  showReset?: boolean;
  leadingActions?: ReactNode;
  trailingActions?: ReactNode;
  summarySlot?: ReactNode;
  className?: string;
  _row?: TData;
}

export interface DataTableSelectionContext<TData> {
  table: Table<TData>;
  selectedRows: TData[];
  selectedCount: number;
  filteredCount: number;
}

export interface DataTableSelectionConfig<TData> {
  enableRowSelection?: boolean;
  actions?: (context: DataTableSelectionContext<TData>) => ReactNode;
  summary?: (context: DataTableSelectionContext<TData>) => ReactNode;
}

export interface DataTableSummaryContext<TData> {
  table: Table<TData>;
  rows: TData[];
  filteredCount: number;
  totalCount: number;
}

export interface DataTablePaginationConfig<TData> {
  enabled?: boolean;
  manual?: boolean;
  totalCount?: number;
  pageSizeOptions?: number[];
  infoLabel?: (context: DataTableSummaryContext<TData>) => ReactNode;
}

export interface DataTableEmptyStateConfig {
  title?: string;
  description?: string;
}

export interface DataTableProps<TData> {
  data: TData[];
  columns: AppColumnDef<TData, unknown>[];
  mode?: DataTableMode;
  state?: Partial<DataTableQueryState>;
  defaultState?: Partial<DataTableQueryState>;
  resetState?: Partial<DataTableQueryState>;
  onStateChange?: (state: DataTableQueryState) => void;
  loading?: boolean;
  error?: ReactNode;
  emptyState?: DataTableEmptyStateConfig;
  toolbar?: false | DataTableToolbarConfig<TData>;
  selection?: DataTableSelectionConfig<TData>;
  summary?: ReactNode | ((context: DataTableSummaryContext<TData>) => ReactNode);
  pagination?: false | DataTablePaginationConfig<TData>;
  className?: string;
  tableClassName?: string;
  containerClassName?: string;
  tableContainerClassName?: string;
  getRowId?: (originalRow: TData, index: number) => string;
}
