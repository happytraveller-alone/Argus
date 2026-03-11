import test from "node:test";
import assert from "node:assert/strict";

import type { RealtimeMergedFindingItem } from "../src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx";
import { mergeRealtimeFindingsBatch } from "../src/pages/AgentAudit/realtimeFindingMerge.ts";

function createFinding(
  overrides: Partial<RealtimeMergedFindingItem> = {},
): RealtimeMergedFindingItem {
  return {
    id: "finding-1",
    merge_key: "todo-1",
    fingerprint: "fingerprint-1",
    title: "hardcoded secret",
    severity: "low",
    display_severity: "low",
    verification_progress: "pending",
    vulnerability_type: "hardcoded_secret",
    file_path: "src/demo.ts",
    line_start: 7,
    line_end: 7,
    confidence: 0.42,
    timestamp: "2026-03-11T00:00:00Z",
    is_verified: false,
    detailMode: "detail",
    ...overrides,
  };
}

test("DB finding can clear a stale false-positive presentation for the same merge key", () => {
  const staleFalsePositive = createFinding({
    id: "event-finding-1",
    display_severity: "invalid",
    verification_progress: "verified",
    authenticity: "false_positive",
    verification_evidence: "event said false positive",
    detailMode: "false_positive_reason",
    timestamp: "2026-03-11T00:00:01Z",
    is_verified: true,
  });
  const dbCorrectedFinding = createFinding({
    id: "db-finding-1",
    display_severity: "high",
    severity: "high",
    verification_progress: "verified",
    authenticity: "confirmed",
    verification_evidence: "db says confirmed",
    detailMode: "detail",
    timestamp: "2026-03-11T00:00:02Z",
    is_verified: true,
  });

  const [merged] = mergeRealtimeFindingsBatch(
    [staleFalsePositive],
    [dbCorrectedFinding],
    { source: "db" },
  );

  assert.equal(merged.id, "db-finding-1");
  assert.equal(merged.display_severity, "high");
  assert.equal(merged.severity, "high");
  assert.equal(merged.authenticity, "confirmed");
  assert.equal(merged.detailMode, "detail");
});
