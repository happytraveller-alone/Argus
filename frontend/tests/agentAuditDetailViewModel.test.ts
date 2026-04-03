import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStatsSummary,
  createTokenUsageAccumulator,
  isVerifiedFinding,
  readAgentAuditFindingsPagination,
  shouldSyncFindingPageFromTableState,
  writeAgentAuditFindingsPagination,
  isVisibleVerifiedVulnerability,
} from "../src/pages/AgentAudit/detailViewModel.ts";
import * as detailViewModel from "../src/pages/AgentAudit/detailViewModel.ts";

test("buildStatsSummary uses the task management progress heuristic for agent detail pages", () => {
  const now = new Date("2026-03-12T08:00:00.000Z");

  const runningSummary = buildStatsSummary({
    task: {
      status: "running",
      created_at: "2026-03-12T07:00:00.000Z",
      started_at: "2026-03-12T07:45:00.000Z",
      progress_percentage: 2,
    },
    displayFindings: [],
    tokenUsage: createTokenUsageAccumulator(),
    now,
  });

  assert.equal(runningSummary.progressPercent, 95);

  const pendingSummary = buildStatsSummary({
    task: {
      status: "pending",
      created_at: "2026-03-12T07:00:00.000Z",
      started_at: null,
      progress_percentage: 88,
    },
    displayFindings: [],
    tokenUsage: createTokenUsageAccumulator(),
    now,
  });

  assert.equal(pendingSummary.progressPercent, 15);
});

test("buildStatsSummary treats terminal agent states as 100 percent regardless of backend progress_percentage", () => {
  const now = new Date("2026-03-12T08:00:00.000Z");

  for (const status of [
    "completed",
    "failed",
    "cancelled",
    "interrupted",
  ]) {
    const summary = buildStatsSummary({
      task: {
        status,
        created_at: "2026-03-12T07:00:00.000Z",
        started_at: "2026-03-12T07:10:00.000Z",
        completed_at: "2026-03-12T07:50:00.000Z",
        progress_percentage: 11,
      },
      displayFindings: [],
      tokenUsage: createTokenUsageAccumulator(),
      now,
    });

    assert.equal(summary.progressPercent, 100, `${status} should show 100%`);
  }
});

test("buildFindingTableState 仅按可见字段筛选，不再命中文件路径和原标题", () => {
  const state = detailViewModel.buildFindingTableState({
    items: [
      {
        id: "finding-1",
        title: "SQL 注入",
        vulnerability_type: "SQL Injection",
        severity: "high",
        display_severity: "high",
        verification_progress: "pending",
        file_path: "src/api/user.ts",
        line_start: 18,
        is_verified: false,
      },
    ],
    filters: {
      keyword: "user.ts",
      severity: "all",
    },
    page: 1,
    pageSize: 10,
  });

  assert.equal(state.totalRows, 0);

  const titleOnlyState = detailViewModel.buildFindingTableState({
    items: [
      {
        id: "finding-1",
        title: "SQL 注入",
        vulnerability_type: "SQL Injection",
        severity: "high",
        display_severity: "high",
        verification_progress: "pending",
        file_path: "src/api/user.ts",
        line_start: 18,
        is_verified: false,
      },
    ],
    filters: {
      keyword: "SQL 注入",
      severity: "all",
    },
    page: 1,
    pageSize: 10,
  });

  assert.equal(titleOnlyState.totalRows, 0);
});

test("calculateResponsiveFindingsPageSize 会随着可用高度增加而返回更多条目", () => {
  assert.equal(
    detailViewModel.calculateResponsiveFindingsPageSize?.(180),
    1,
  );
  assert.equal(
    detailViewModel.calculateResponsiveFindingsPageSize?.(360),
    4,
  );
  assert.equal(
    detailViewModel.calculateResponsiveFindingsPageSize?.(520),
    7,
  );
});

test("agent audit findings pagination helpers preserve page state in route search", () => {
  const parsed = readAgentAuditFindingsPagination(
    new URLSearchParams("returnTo=%2Ftasks%2Fintelligent&findingsPage=3&findingsPageSize=7"),
  );

  assert.deepEqual(parsed, {
    page: 3,
    pageSize: 7,
  });

  const next = writeAgentAuditFindingsPagination(
    new URLSearchParams("returnTo=%2Ftasks%2Fintelligent&detailType=finding&detailId=finding-1"),
    {
      page: 4,
      pageSize: 9,
    },
  );

  assert.equal(next.get("returnTo"), "/tasks/intelligent");
  assert.equal(next.get("detailType"), "finding");
  assert.equal(next.get("detailId"), "finding-1");
  assert.equal(next.get("findingsPage"), "4");
  assert.equal(next.get("findingsPageSize"), "9");
});

test("agent audit findings pagination helpers fall back for invalid values and clear defaults", () => {
  const parsed = readAgentAuditFindingsPagination(
    new URLSearchParams("findingsPage=0&findingsPageSize=NaN"),
  );

  assert.deepEqual(parsed, {
    page: 1,
    pageSize: detailViewModel.AGENT_AUDIT_FINDINGS_PAGE_SIZE,
  });

  const next = writeAgentAuditFindingsPagination(
    new URLSearchParams("findingsPage=6&findingsPageSize=11"),
    {
      page: 1,
      pageSize: detailViewModel.AGENT_AUDIT_FINDINGS_PAGE_SIZE,
    },
  );

  assert.equal(next.has("findingsPage"), false);
  assert.equal(next.has("findingsPageSize"), false);
});

test("loading state should not eagerly reset agent audit finding page from URL", () => {
  assert.equal(
    shouldSyncFindingPageFromTableState({
      requestedPage: 3,
      resolvedPage: 1,
      totalRows: 0,
      isLoading: true,
    }),
    false,
  );
});

test("loaded finding table may clamp invalid page after data is ready", () => {
  assert.equal(
    shouldSyncFindingPageFromTableState({
      requestedPage: 3,
      resolvedPage: 1,
      totalRows: 1,
      isLoading: false,
    }),
    true,
  );
});

test("isVerifiedFinding 识别 is_verified 和 verification_progress", () => {
  assert.equal(isVerifiedFinding({ id: "pending-1" }), false);
  assert.equal(isVerifiedFinding({ id: "verified-1", is_verified: true }), true);
  assert.equal(
    isVerifiedFinding({
      id: "verified-2",
      is_verified: false,
      verification_progress: "verified",
    }),
    true,
  );
});

test("getAgentAuditFindingDisplayStatus 不再把 likely 直接显示为确报", () => {
  assert.equal(
    detailViewModel.getAgentAuditFindingDisplayStatus({
      id: "likely-1",
      status: "likely",
      is_verified: false,
      verification_progress: "pending",
    }),
    "open",
  );
  assert.equal(detailViewModel.getAgentAuditFindingStatusLabel("open"), "待确认");
});

test("isVisibleVerifiedVulnerability 会过滤各类误报信号", () => {
  const base = {
    id: "finding-1",
    is_verified: true,
    verification_progress: "verified",
  };

  assert.equal(
    isVisibleVerifiedVulnerability({
      ...base,
      authenticity: "false_positive",
    }),
    false,
  );
  assert.equal(
    isVisibleVerifiedVulnerability({
      ...base,
      status: "false_positive",
    }),
    false,
  );
  assert.equal(
    isVisibleVerifiedVulnerability({
      ...base,
      detailMode: "false_positive_reason",
    }),
    false,
  );
  assert.equal(
    isVisibleVerifiedVulnerability({
      ...base,
      display_severity: "invalid",
    }),
    false,
  );
  assert.equal(
    isVisibleVerifiedVulnerability({
      ...base,
      display_severity: "high",
      confidence: 0.92,
    }),
    true,
  );
  assert.equal(
    isVisibleVerifiedVulnerability({
      ...base,
      display_severity: "high",
      confidence: null,
    }),
    false,
  );
});

test("buildStatsSummary 统计当前管理列表中的非误报漏洞", () => {
  const summary = buildStatsSummary({
    task: {
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      started_at: "2026-03-12T07:10:00.000Z",
      completed_at: "2026-03-12T07:50:00.000Z",
      findings_count: 99,
      verified_count: 4,
      false_positive_count: 10,
    },
    displayFindings: [
      {
        id: "verified-1",
        is_verified: true,
        display_severity: "high",
        confidence: 0.92,
      },
      {
        id: "verified-2",
        verification_progress: "verified",
        display_severity: "medium",
        confidence: 0.67,
      },
      {
        id: "pending-1",
        verification_progress: "pending",
        display_severity: "critical",
        confidence: 0.88,
      },
      {
        id: "false-positive-1",
        is_verified: true,
        authenticity: "false_positive",
        display_severity: "low",
        confidence: 0.42,
      },
      {
        id: "false-positive-2",
        verification_progress: "verified",
        display_severity: "invalid",
        confidence: 0.31,
      },
    ],
    tokenUsage: createTokenUsageAccumulator(),
    now: new Date("2026-03-12T08:00:00.000Z"),
  });

  assert.equal(summary.totalFindings, 3);
  assert.equal(summary.effectiveFindings, 3);
  assert.equal(summary.falsePositiveFindings, 2);
});

test("buildStatsSummary 在无展示数据时回退到 task.findings_count 和 false_positive_count", () => {
  const summary = buildStatsSummary({
    task: {
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      started_at: "2026-03-12T07:10:00.000Z",
      completed_at: "2026-03-12T07:50:00.000Z",
      findings_count: 12,
      verified_count: 3,
      false_positive_count: 9,
    },
    displayFindings: [],
    tokenUsage: createTokenUsageAccumulator(),
    now: new Date("2026-03-12T08:00:00.000Z"),
  });

  assert.equal(summary.totalFindings, 12);
  assert.equal(summary.effectiveFindings, 12);
  assert.equal(summary.falsePositiveFindings, 9);
});
