/**
 * Phase G tests — findingDetail.intelligent.legacyAllUndefined (AC6 / N2)
 *
 * Exercises buildAgentFindingDetailModel with a legacy intelligent finding
 * where all four new fields (cweId, scopeType, module, resolvedFilePath) are
 * undefined/null — simulating an old DB row produced before Phase A.
 *
 * Pure unit test against the model builder; no React rendering required.
 * Uses Node built-in test runner (same as agentAuditDetail.test.tsx pattern).
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAgentFindingDetailModel,
} from "../src/pages/finding-detail/viewModel.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Minimal AgentFinding shape with all new Phase A fields absent (legacy row).
 *
 * AgentFinding requires id + task_id at minimum (index signature allows extras).
 * The four new Phase A fields (cweId, scopeType, module, resolvedFilePath)
 * intentionally absent — simulates a pre-Phase-A DB row.
 */
function makeLegacyAgentFinding(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "legacy-001",
    task_id: "task-001",
    severity: "high",
    description_markdown: "## 漏洞描述\nlegacy description",
    ai_confidence: 0.7,
    // cwe_id absent (the old AgentFinding field) → canonical typeLabel = "CWE 未识别"
    cwe_id: undefined,
    file_path: "src/legacy.rs",
    line_start: 10,
    line_end: 20,
    status: "open",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// findingDetail.intelligent.legacyAllUndefined  (AC6 / N2)
// ---------------------------------------------------------------------------

test("findingDetail.intelligent.legacyAllUndefined — no crash and CWE未识别 in trackingItems", () => {
  const finding = makeLegacyAgentFinding() as never;

  // Must not throw
  let model: ReturnType<typeof buildAgentFindingDetailModel>;
  assert.doesNotThrow(() => {
    model = buildAgentFindingDetailModel({
      finding,
      taskId: "task-001",
      findingId: "legacy-001",
      projectName: "argus",
      llmModel: "claude-3-5-sonnet",
      projectRoot: null,
    });
  }, "buildAgentFindingDetailModel must not throw on legacy finding");

  // trackingItems must contain a "漏洞类型" entry with value "CWE 未识别"
  const allItems = [
    ...(model!.trackingItems ?? []),
    ...(model!.overviewItems ?? []),
  ];
  const typeItem = allItems.find((item) => item.label === "漏洞类型");
  assert.ok(typeItem, "trackingItems must contain a 漏洞类型 entry");
  assert.equal(typeItem!.value, "CWE 未识别", `漏洞类型 must be CWE 未识别 for legacy row; got: ${typeItem!.value}`);
});

test("findingDetail.intelligent.legacyAllUndefined — vuln_class never substituted when cweId absent", () => {
  // Even if finding has vulnerability_type set, typeLabel must still be CWE 未识别
  const finding = makeLegacyAgentFinding({ vulnerability_type: "xss_injection" }) as never;

  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "task-002",
    findingId: "legacy-002",
    projectName: "argus",
    llmModel: "claude-3-5-sonnet",
    projectRoot: null,
  });

  const allItems = [
    ...(model.trackingItems ?? []),
    ...(model.overviewItems ?? []),
  ];
  const typeItem = allItems.find((item) => item.label === "漏洞类型");
  assert.ok(typeItem, "漏洞类型 item must exist");
  assert.equal(typeItem!.value, "CWE 未识别");

  // xss_injection must not appear anywhere in tracking/overview items
  const allValues = allItems.map((i) => String(i.value || "")).join("|");
  assert.ok(!allValues.includes("xss_injection"), `vuln_class must not appear in items; got: ${allValues}`);
});
