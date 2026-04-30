import type { ExportOptions, ReportFormat } from "./components";

export interface ReportExportRequestParams {
  format: ReportFormat;
  include_code_snippets: boolean;
  include_remediation: boolean;
  include_metadata: boolean;
  compact_mode: boolean;
}

export function buildReportExportParams(
  format: ReportFormat,
  options: ExportOptions,
): ReportExportRequestParams {
  return {
    format,
    include_code_snippets: options.includeCodeSnippets,
    include_remediation: options.includeRemediation,
    include_metadata: options.includeMetadata,
    compact_mode: options.compactMode,
  };
}

export function buildReportPreviewCacheKey(
  format: ReportFormat,
  options: ExportOptions,
): string {
  return JSON.stringify(buildReportExportParams(format, options));
}
