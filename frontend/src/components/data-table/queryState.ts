import type { Updater } from "@tanstack/react-table";
import { functionalUpdate } from "@tanstack/react-table";
import type {
  DataTableDensity,
  DataTableFilterValue,
  DataTableQueryState,
} from "./types";

export const DEFAULT_DATA_TABLE_DENSITY: DataTableDensity = "comfortable";

export function normalizePageSize(value?: number): number {
  if (!Number.isFinite(value) || Number(value) <= 0) {
    return 10;
  }
  return Math.max(1, Math.floor(Number(value)));
}

export function createDefaultDataTableState(
  overrides: Partial<DataTableQueryState> = {},
): DataTableQueryState {
  return {
    globalFilter: overrides.globalFilter ?? "",
    columnFilters: overrides.columnFilters ?? [],
    sorting: overrides.sorting ?? [],
    pagination: {
      pageIndex: overrides.pagination?.pageIndex ?? 0,
      pageSize: normalizePageSize(overrides.pagination?.pageSize),
    },
    columnVisibility: overrides.columnVisibility ?? {},
    rowSelection: overrides.rowSelection ?? {},
    density: overrides.density ?? DEFAULT_DATA_TABLE_DENSITY,
  };
}

export function resolveDataTableState(
  baseState: DataTableQueryState,
  partialState?: Partial<DataTableQueryState>,
): DataTableQueryState {
  if (!partialState) return baseState;
  return createDefaultDataTableState({
    ...baseState,
    ...partialState,
    pagination: {
      ...baseState.pagination,
      ...partialState.pagination,
    },
  });
}

export function applyDataTableStateUpdate(
  state: DataTableQueryState,
  updater: Updater<DataTableQueryState>,
): DataTableQueryState {
  return createDefaultDataTableState(functionalUpdate(updater, state));
}

export function setSingleColumnSorting(
  state: DataTableQueryState,
  columnId: string,
  desc: boolean,
): DataTableQueryState {
  return {
    ...state,
    sorting: columnId ? [{ id: columnId, desc }] : [],
  };
}

export function setColumnFilterValue(
  state: DataTableQueryState,
  columnId: string,
  value: DataTableFilterValue,
): DataTableQueryState {
  const nextFilters = state.columnFilters.filter((filter) => filter.id !== columnId);
  const isEmptyArray = Array.isArray(value) && value.length === 0;
  const isEmptyObject =
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).length === 0;
  if (
    value !== undefined &&
    value !== null &&
    value !== "" &&
    value !== false &&
    !isEmptyArray &&
    !isEmptyObject
  ) {
    nextFilters.push({ id: columnId, value });
  }

  return {
    ...state,
    columnFilters: nextFilters,
    pagination: {
      ...state.pagination,
      pageIndex: 0,
    },
    rowSelection: {},
  };
}

export function resetDataTableFilters(
  state: DataTableQueryState,
): DataTableQueryState {
  return {
    ...state,
    globalFilter: "",
    columnFilters: [],
    rowSelection: {},
    pagination: {
      ...state.pagination,
      pageIndex: 0,
    },
  };
}

export function hasActiveDataTableFilters(state: DataTableQueryState): boolean {
  return Boolean(state.globalFilter) || state.columnFilters.length > 0;
}

export function areDataTableQueryStatesEqual(
  left: DataTableQueryState,
  right: DataTableQueryState,
): boolean {
  return (
    JSON.stringify(createDefaultDataTableState(left)) ===
    JSON.stringify(createDefaultDataTableState(right))
  );
}
