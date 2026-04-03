import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const dialogPath =
  "/home/xyf/AuditTool/frontend/src/pages/AgentAudit/components/ReportExportDialog.tsx";

test("ReportExportDialog 文案不再把导出结果描述为仅已验证漏洞", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.doesNotMatch(source, /已验证漏洞/);
  assert.doesNotMatch(source, /已验证=全部导出结果/);
});
