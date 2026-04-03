import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAgentAuditTaskFindingCountersPatch,
  summarizeAgentAuditFindings,
} from "../src/pages/AgentAudit/detailViewModel.ts";

test("summarizeAgentAuditFindings 区分待确认、确报和误报并分别统计严重度", () => {
  const summary = summarizeAgentAuditFindings([
    {
      id: "verified-1",
      severity: "high",
      status: "verified",
      is_verified: true,
      verification_progress: "verified",
    },
    {
      id: "pending-1",
      severity: "critical",
      status: "needs_review",
      is_verified: false,
      verification_progress: "pending",
    },
    {
      id: "fp-1",
      severity: "low",
      status: "false_positive",
      is_verified: false,
      authenticity: "false_positive",
      verification_progress: "verified",
    },
  ]);

  assert.deepEqual(summary.statusCounts, {
    pending: 1,
    verified: 1,
    false_positive: 1,
  });
  assert.equal(summary.findingsCount, 2);
  assert.equal(summary.verifiedCount, 1);
  assert.equal(summary.falsePositiveCount, 1);
  assert.deepEqual(summary.severityCounts, {
    critical: 1,
    high: 1,
    medium: 0,
    low: 1,
    info: 0,
  });
  assert.deepEqual(summary.effectiveSeverityCounts, {
    critical: 1,
    high: 1,
    medium: 0,
    low: 0,
    info: 0,
  });
  assert.deepEqual(summary.verifiedSeverityCounts, {
    critical: 0,
    high: 1,
    medium: 0,
    low: 0,
  });
});

test("buildAgentAuditTaskFindingCountersPatch 覆盖判真判假后的 task counters 和 defect_summary", () => {
  const patch = buildAgentAuditTaskFindingCountersPatch({
    task: {
      findings_count: 99,
      verified_count: 12,
      false_positive_count: 7,
      defect_summary: {
        scope: "all_findings",
        total_count: 106,
        severity_counts: {
          critical: 9,
          high: 10,
          medium: 11,
          low: 12,
          info: 13,
        },
        status_counts: {
          pending: 80,
          verified: 12,
          false_positive: 14,
        },
      },
    },
    findings: [
      {
        id: "verified-now",
        severity: "medium",
        status: "verified",
        is_verified: true,
        verification_progress: "verified",
      },
      {
        id: "false-positive-now",
        severity: "high",
        status: "false_positive",
        is_verified: false,
        authenticity: "false_positive",
      },
    ],
  });

  assert.deepEqual(patch, {
    findings_count: 1,
    verified_count: 1,
    false_positive_count: 1,
    critical_count: 0,
    high_count: 0,
    medium_count: 1,
    low_count: 0,
    verified_critical_count: 0,
    verified_high_count: 0,
    verified_medium_count: 1,
    verified_low_count: 0,
    defect_summary: {
      scope: "all_findings",
      total_count: 2,
      severity_counts: {
        critical: 0,
        high: 1,
        medium: 1,
        low: 0,
        info: 0,
      },
      status_counts: {
        pending: 0,
        verified: 1,
        false_positive: 1,
      },
    },
  });
});

test("buildAgentAuditTaskFindingCountersPatch 对单条漏洞状态切换保持口径一致", () => {
  const scenarios = [
    {
      name: "pending -> verified",
      finding: {
        id: "verified-1",
        severity: "high",
        status: "verified",
        is_verified: true,
        verification_progress: "verified",
      },
      expected: {
        findings_count: 1,
        verified_count: 1,
        false_positive_count: 0,
        high_count: 1,
        verified_high_count: 1,
        pending: 0,
        verified: 1,
        false_positive: 0,
      },
    },
    {
      name: "pending -> false_positive",
      finding: {
        id: "fp-1",
        severity: "high",
        status: "false_positive",
        is_verified: false,
        authenticity: "false_positive",
      },
      expected: {
        findings_count: 0,
        verified_count: 0,
        false_positive_count: 1,
        high_count: 0,
        verified_high_count: 0,
        pending: 0,
        verified: 0,
        false_positive: 1,
      },
    },
    {
      name: "false_positive -> verified",
      finding: {
        id: "verified-2",
        severity: "critical",
        status: "verified",
        is_verified: true,
        verification_progress: "verified",
      },
      expected: {
        findings_count: 1,
        verified_count: 1,
        false_positive_count: 0,
        high_count: 0,
        verified_high_count: 0,
        pending: 0,
        verified: 1,
        false_positive: 0,
      },
    },
    {
      name: "verified -> false_positive",
      finding: {
        id: "fp-2",
        severity: "critical",
        status: "false_positive",
        is_verified: false,
        authenticity: "false_positive",
      },
      expected: {
        findings_count: 0,
        verified_count: 0,
        false_positive_count: 1,
        high_count: 0,
        verified_high_count: 0,
        pending: 0,
        verified: 0,
        false_positive: 1,
      },
    },
  ];

  for (const scenario of scenarios) {
    const patch = buildAgentAuditTaskFindingCountersPatch({
      task: null,
      findings: [scenario.finding],
    });

    assert.equal(patch.findings_count, scenario.expected.findings_count, scenario.name);
    assert.equal(patch.verified_count, scenario.expected.verified_count, scenario.name);
    assert.equal(
      patch.false_positive_count,
      scenario.expected.false_positive_count,
      scenario.name,
    );
    assert.equal(patch.high_count, scenario.expected.high_count, scenario.name);
    assert.equal(
      patch.verified_high_count,
      scenario.expected.verified_high_count,
      scenario.name,
    );
    assert.deepEqual(
      patch.defect_summary.status_counts,
      {
        pending: scenario.expected.pending,
        verified: scenario.expected.verified,
        false_positive: scenario.expected.false_positive,
      },
      scenario.name,
    );
  }
});
