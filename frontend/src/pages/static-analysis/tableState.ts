import {
  createDefaultDataTableState,
  type DataTableQueryState,
} from "@/components/data-table";

const DEFAULT_PAGE_SIZE = 15;

export function resolveStaticAnalysisTableState(
  initialState: DataTableQueryState,
): DataTableQueryState {
  return createDefaultDataTableState({
    ...initialState,
    sorting:
      initialState.sorting.length > 0
        ? initialState.sorting
        : [{ id: "severity", desc: true }],
    pagination: {
      pageIndex: initialState.pagination.pageIndex,
      pageSize: initialState.pagination.pageSize || DEFAULT_PAGE_SIZE,
    },
    columnVisibility: {
      ...initialState.columnVisibility,
      location: false,
    },
  });
}

export function createStaticAnalysisInitialTableState(
  initialState: DataTableQueryState,
): DataTableQueryState {
  return resolveStaticAnalysisTableState(initialState);
}
