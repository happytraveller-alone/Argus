import { stripSupportedArchiveSuffix } from "@/features/projects/services/repoZipScan";

export const DEFAULT_SCAN_EXCLUDES = [
  "node_modules/**",
  ".git/**",
  "dist/**",
  "build/**",
  "*.log",
];

export function stripScanArchiveSuffix(filename: string) {
  return stripSupportedArchiveSuffix(filename);
}

export function extractCreateScanTaskApiErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    const detail = (error as any)?.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const msgs = detail
        .map((item: any) =>
          typeof item?.msg === "string" ? item.msg : String(item),
        )
        .filter(Boolean);
      if (msgs.length > 0) return msgs.join("; ");
    }
    return error.message || "未知错误";
  }
  const detail = (error as any)?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return "未知错误";
}
