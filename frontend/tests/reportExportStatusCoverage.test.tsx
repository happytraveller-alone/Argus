import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const dialogPath = new URL(
  "../src/pages/AgentAudit/components/ReportExportDialog.tsx",
  import.meta.url,
);

test("ReportExportDialog 文案不再把导出结果描述为仅已验证漏洞", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.doesNotMatch(source, /已验证漏洞/);
  assert.doesNotMatch(source, /已验证=全部导出结果/);
});
