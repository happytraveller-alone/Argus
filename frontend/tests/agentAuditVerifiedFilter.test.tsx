import test from "node:test";
import assert from "node:assert/strict";

import {
  hasAnyVerifiedFinding,
  isVerifiedFinding,
  shouldAutoApplyVerifiedFilter,
} from "../src/pages/AgentAudit/findingsFilterUtils";
import type { RealtimeMergedFindingItem } from "../src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx";

function createFinding(
  overrides: Partial<RealtimeMergedFindingItem> = {},
): RealtimeMergedFindingItem {
  return {
    id: overrides.id ?? "finding-1",
    fingerprint: overrides.fingerprint ?? "fingerprint-1",
    title: overrides.title ?? "SQL Injection",
    severity: overrides.severity ?? "high",
    display_severity: overrides.display_severity ?? "high",
    verification_progress: overrides.verification_progress ?? "pending",
    vulnerability_type: overrides.vulnerability_type ?? "SQL Injection",
    is_verified: overrides.is_verified ?? false,
    ...overrides,
  } as RealtimeMergedFindingItem;
}

test("isVerifiedFinding 识别 is_verified 和 verification_progress", () => {
  assert.equal(isVerifiedFinding(createFinding()), false);
  assert.equal(
    isVerifiedFinding(createFinding({ is_verified: true })),
    true,
  );
  assert.equal(
    isVerifiedFinding(
      createFinding({ verification_progress: "verified", is_verified: false }),
    ),
    true,
  );
});

test("hasAnyVerifiedFinding 在实时或持久结果中存在已验证项时返回 true", () => {
  const persisted = [createFinding({ id: "p1" })];
  const realtime = [createFinding({ id: "r1", is_verified: true })];
  assert.equal(hasAnyVerifiedFinding({ persisted, realtime }), true);
  assert.equal(
    hasAnyVerifiedFinding({ persisted, realtime: [createFinding({ id: "r2" })] }),
    false,
  );
});

test("shouldAutoApplyVerifiedFilter 仅在满足全部条件时返回 true", () => {
  assert.equal(
    shouldAutoApplyVerifiedFilter({
      hasVerifiedFinding: false,
      userOverride: false,
      alreadyApplied: false,
      currentVerificationFilter: "all",
    }),
    false,
  );
  assert.equal(
    shouldAutoApplyVerifiedFilter({
      hasVerifiedFinding: true,
      userOverride: true,
      alreadyApplied: false,
      currentVerificationFilter: "all",
    }),
    false,
  );
  assert.equal(
    shouldAutoApplyVerifiedFilter({
      hasVerifiedFinding: true,
      userOverride: false,
      alreadyApplied: true,
      currentVerificationFilter: "all",
    }),
    false,
  );
  assert.equal(
    shouldAutoApplyVerifiedFilter({
      hasVerifiedFinding: true,
      userOverride: false,
      alreadyApplied: false,
      currentVerificationFilter: "verified",
    }),
    false,
  );
  assert.equal(
    shouldAutoApplyVerifiedFilter({
      hasVerifiedFinding: true,
      userOverride: false,
      alreadyApplied: false,
      currentVerificationFilter: "all",
    }),
    true,
  );
});
