import type { DataTableQueryState } from "@/components/data-table";

export type DeletedFilterValue = "false" | "true" | "all";

export function resolveDeletedFilterValue(
  state: DataTableQueryState,
  columnId = "deletedStatus",
): DeletedFilterValue {
  const value = state.columnFilters.find((filter) => filter.id === columnId)?.value;
  return value === "false" || value === "true" || value === "all" ? value : "all";
}
