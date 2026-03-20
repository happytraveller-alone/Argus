import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { DataTableQueryState } from "./types";
import { createDefaultDataTableState } from "./queryState";

function deserializeFilters(
  raw: string | null,
): DataTableQueryState["columnFilters"] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return Object.entries(parsed).map(([id, value]) => ({ id, value }));
  } catch {
    return [];
  }
}

function serializeFilters(state: DataTableQueryState["columnFilters"]): string {
  const payload = Object.fromEntries(
    state
      .filter((filter) => filter.value !== undefined && filter.value !== "")
      .map((filter) => [filter.id, filter.value]),
  );
  return JSON.stringify(payload);
}

export function parseDataTableUrlState(
  params: URLSearchParams,
): DataTableQueryState {
  const page = Math.max(1, Number(params.get("page") || "1")) - 1;
  const pageSize = Math.max(1, Number(params.get("pageSize") || "10"));
  const sort = String(params.get("sort") || "").trim();
  const order = String(params.get("order") || "asc").trim().toLowerCase();
  return createDefaultDataTableState({
    globalFilter: String(params.get("q") || ""),
    sorting: sort ? [{ id: sort, desc: order === "desc" }] : [],
    pagination: {
      pageIndex: Number.isFinite(page) ? page : 0,
      pageSize,
    },
    columnFilters: deserializeFilters(params.get("filters")),
  });
}

export function serializeDataTableUrlState(
  state: Partial<DataTableQueryState>,
): URLSearchParams {
  const params = new URLSearchParams();
  const globalFilter = String(state.globalFilter || "").trim();
  if (globalFilter) {
    params.set("q", globalFilter);
  }

  const sorting = state.sorting ?? [];
  if (sorting.length > 0) {
    params.set("sort", sorting[0]?.id ?? "");
    params.set("order", sorting[0]?.desc ? "desc" : "asc");
  }

  const pageIndex = state.pagination?.pageIndex ?? 0;
  const pageSize = state.pagination?.pageSize ?? 10;
  if (pageIndex > 0) {
    params.set("page", String(pageIndex + 1));
  }
  if (pageSize !== 10) {
    params.set("pageSize", String(pageSize));
  }

  const filters = state.columnFilters ?? [];
  if (filters.length > 0) {
    const serialized = serializeFilters(filters);
    if (serialized !== "{}") {
      params.set("filters", serialized);
    }
  }

  return params;
}

export function mergeDataTableUrlState(
  params: URLSearchParams,
  state: Partial<DataTableQueryState>,
): URLSearchParams {
  const nextParams = new URLSearchParams(params);
  ["q", "sort", "order", "page", "pageSize", "filters"].forEach((key) => {
    nextParams.delete(key);
  });
  const serialized = serializeDataTableUrlState(state);
  serialized.forEach((value, key) => {
    nextParams.set(key, value);
  });
  return nextParams;
}

export function useDataTableUrlState(enabled = true) {
  const [searchParams, setSearchParams] = useSearchParams();

  const initialState = useMemo(() => {
    if (!enabled) return createDefaultDataTableState();
    return parseDataTableUrlState(searchParams);
  }, [enabled, searchParams]);

  const syncStateToUrl = useCallback(
    (state: Partial<DataTableQueryState>) => {
      if (!enabled) return;
      setSearchParams(
        (current) => mergeDataTableUrlState(new URLSearchParams(current), state),
        { replace: true },
      );
    },
    [enabled, setSearchParams],
  );

  return {
    initialState,
    syncStateToUrl,
  };
}
