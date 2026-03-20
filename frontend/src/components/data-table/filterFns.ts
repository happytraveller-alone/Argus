import type { FilterFn } from "@tanstack/react-table";
import type { DataTableNumberRangeValue } from "./types";

export function textIncludesFilter(
  candidate: unknown,
  query: unknown,
): boolean {
  const candidateText = String(candidate ?? "").toLowerCase();
  const queryText = String(query ?? "").trim().toLowerCase();
  if (!queryText) return true;
  return candidateText.includes(queryText);
}

export function facetFilter(
  candidate: unknown,
  filterValue: unknown,
): boolean {
  if (filterValue === undefined || filterValue === null || filterValue === "") {
    return true;
  }
  if (Array.isArray(filterValue)) {
    if (filterValue.length === 0) return true;
    return filterValue.includes(String(candidate ?? ""));
  }
  if (typeof filterValue === "boolean") {
    return Boolean(candidate) === filterValue;
  }
  return String(candidate ?? "") === String(filterValue);
}

export function numberRangeFilter(
  candidate: unknown,
  range: DataTableNumberRangeValue,
): boolean {
  if (candidate === undefined || candidate === null || candidate === "") {
    return false;
  }
  const numericValue = Number(candidate);
  if (!Number.isFinite(numericValue)) {
    return false;
  }
  if (range.min !== undefined && numericValue < range.min) {
    return false;
  }
  if (range.max !== undefined && numericValue > range.max) {
    return false;
  }
  return true;
}

export const tanstackTextIncludesFilter: FilterFn<any> = (row, columnId, value) =>
  textIncludesFilter(row.getValue(columnId), value);

export const tanstackFacetFilter: FilterFn<any> = (row, columnId, value) =>
  facetFilter(row.getValue(columnId), value);

export const tanstackNumberRangeFilter: FilterFn<any> = (
  row,
  columnId,
  value: DataTableNumberRangeValue,
) => numberRangeFilter(row.getValue(columnId), value || {});
