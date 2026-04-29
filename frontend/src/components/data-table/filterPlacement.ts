import type {
  DataTableColumnMeta,
  DataTableFilterPlacement,
  DataTableFilterVariant,
} from "./types";

export function isHeaderDataTableFilterVariant(
  variant?: DataTableFilterVariant,
): variant is "text" | "select" | "multi-select" | "boolean" | "number-range" {
  return (
    variant === "text" ||
    variant === "select" ||
    variant === "multi-select" ||
    variant === "boolean" ||
    variant === "number-range"
  );
}

export function resolveDataTableFilterPlacement(
  meta?: DataTableColumnMeta,
): DataTableFilterPlacement | "none" {
  const variant = meta?.filterVariant;
  if (!variant) return "none";
  if (meta?.filterPlacement && meta.filterPlacement !== "auto") {
    return meta.filterPlacement;
  }
  return isHeaderDataTableFilterVariant(variant) ? "header" : "none";
}
