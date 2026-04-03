import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("ReportExportDialog 导出请求会携带当前导出选项并按选项区分预览缓存", () => {
  const source = readFileSync(
    "/home/xyf/AuditTool/frontend/src/pages/AgentAudit/components/ReportExportDialog.tsx",
    "utf8",
  );

  assert.match(source, /buildReportExportParams/);
  assert.match(source, /buildReportPreviewCacheKey/);
  assert.match(source, /const reportRevision = useMemo/);
  assert.match(source, /const requestFormat = format === "pdf" \? "markdown" : format;/);
  assert.match(source, /previewCache\.current\.has\(cacheKey\)/);
  assert.match(source, /previewCache\.current\.get\(cacheKey\)/);
  assert.match(source, /previewCache\.current\.set\(cacheKey,\s*content\)/);
  assert.match(source, /buildReportPreviewCacheKey\(format,\s*exportOptions\)\}::\$\{task\.id\}::\$\{reportRevision\}/);
  assert.match(source, /params:\s*buildReportExportParams\(requestFormat,\s*exportOptions\)/);
  assert.match(source, /params:\s*buildReportExportParams\("pdf",\s*exportOptions\)/);
});
