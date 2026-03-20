import type {
  DataTableColumnMeta,
  DataTableFilterPlacement,
  DataTableFilterVariant,
} from "./types";

export function isHeaderDataTableFilterVariant(
  variant?: DataTableFilterVariant,
): variant is "select" | "multi-select" | "boolean" {
  return variant === "select" || variant === "multi-select" || variant === "boolean";
}

export function resolveDataTableFilterPlacement(
  meta?: DataTableColumnMeta,
): DataTableFilterPlacement | "none" {
  const variant = meta?.filterVariant;
  if (!variant) return "none";
  if (meta?.filterPlacement && meta.filterPlacement !== "auto") {
    return meta.filterPlacement;
  }
  return isHeaderDataTableFilterVariant(variant) ? "header" : "toolbar";
}
