import type { DataTableDensity } from "./types";

export const DATA_TABLE_DENSITY_LABELS: Record<DataTableDensity, string> = {
  compact: "紧凑",
  comfortable: "舒适",
  spacious: "宽松",
};

export const DATA_TABLE_DENSITY_CELL_CLASS: Record<DataTableDensity, string> = {
  compact: "py-2 text-sm",
  comfortable: "py-3 text-sm",
  spacious: "py-4 text-base",
};
