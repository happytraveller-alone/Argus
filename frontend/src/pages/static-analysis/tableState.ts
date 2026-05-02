import {
  createDefaultDataTableState,
  type DataTableQueryState,
} from "@/components/data-table";

const DEFAULT_PAGE_SIZE = 15;

export function resolveStaticAnalysisTableState(
  initialState: Partial<DataTableQueryState> = {},
): DataTableQueryState {
  const normalizedState = createDefaultDataTableState(initialState);
  return createDefaultDataTableState({
    ...normalizedState,
    sorting:
      normalizedState.sorting.length > 0
        ? normalizedState.sorting
        : [{ id: "severity", desc: true }],
    pagination: {
      pageIndex: normalizedState.pagination.pageIndex,
      pageSize: initialState.pagination?.pageSize || DEFAULT_PAGE_SIZE,
    },
    columnVisibility: {
      ...normalizedState.columnVisibility,
      location: false,
    },
  });
}

export function createStaticAnalysisInitialTableState(
  initialState: Partial<DataTableQueryState> = {},
): DataTableQueryState {
  return resolveStaticAnalysisTableState(initialState);
}
