import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStaticAnalysisProgressSummary,
  buildStaticAnalysisListState,
  buildUnifiedFindingRows,
  formatStaticAnalysisDuration,
} from "../src/pages/static-analysis/viewModel.ts";

test("buildUnifiedFindingRows normalizes opengrep and gitleaks rows", () => {
  const rows = buildUnifiedFindingRows({
    opengrepFindings: [
      {
        id: "og-1",
        scan_task_id: "task-og",
        severity: "HIGH",
        confidence: "LOW",
        file_path: "/tmp/workdir/repo/src/auth.ts",
        start_line: 12,
        status: "verified",
        rule_name: "auth-rule",
      },
    ],
    gitleaksFindings: [
      {
        id: "gl-1",
        scan_task_id: "task-gl",
        rule_id: "gitleaks-rule",
        file_path: "secret.env",
        start_line: 7,
        status: "open",
      },
    ],
    opengrepTaskId: "task-og",
    gitleaksTaskId: "task-gl",
  });

  assert.equal(rows[0]?.engine, "opengrep");
  assert.equal(rows[0]?.filePath, "repo/src/auth.ts");
  assert.equal(rows[0]?.severity, "HIGH");
  assert.equal(rows[0]?.confidence, "LOW");

  assert.equal(rows[1]?.engine, "gitleaks");
  assert.equal(rows[1]?.severity, "LOW");
  assert.equal(rows[1]?.confidence, "MEDIUM");
});

test("buildStaticAnalysisListState filters, sorts and paginates rows", () => {
  const rows = [
    {
      key: "a",
      id: "a",
      taskId: "1",
      engine: "opengrep",
      rule: "rule-a",
      filePath: "src/z.ts",
      line: 20,
      severity: "HIGH",
      severityScore: 3,
      confidence: "LOW",
      confidenceScore: 1,
      status: "open",
    },
    {
      key: "b",
      id: "b",
      taskId: "1",
      engine: "opengrep",
      rule: "rule-b",
      filePath: "src/a.ts",
      line: 8,
      severity: "HIGH",
      severityScore: 3,
      confidence: "HIGH",
      confidenceScore: 3,
      status: "verified",
    },
    {
      key: "c",
      id: "c",
      taskId: "2",
      engine: "gitleaks",
      rule: "rule-c",
      filePath: "src/a.ts",
      line: 4,
      severity: "LOW",
      severityScore: 1,
      confidence: "MEDIUM",
      confidenceScore: 2,
      status: "open",
    },
  ] as const;

  const state = buildStaticAnalysisListState({
    rows: [...rows],
    engineFilter: "all",
    statusFilter: "all",
    confidenceFilter: "all",
    page: 1,
    pageSize: 2,
  });

  assert.equal(state.totalRows, 3);
  assert.equal(state.totalPages, 2);
  assert.deepEqual(
    state.pagedRows.map((row) => row.key),
    ["b", "a"],
  );

  const filtered = buildStaticAnalysisListState({
    rows: [...rows],
    engineFilter: "opengrep",
    statusFilter: "verified",
    confidenceFilter: "HIGH",
    page: 1,
    pageSize: 10,
  });

  assert.deepEqual(
    filtered.pagedRows.map((row) => row.key),
    ["b"],
  );
});

test("formatStaticAnalysisDuration formats milliseconds into readable labels", () => {
  assert.equal(formatStaticAnalysisDuration(12), "12 ms");
  assert.equal(formatStaticAnalysisDuration(1200), "1.20 s");
  assert.equal(formatStaticAnalysisDuration(61_000), "1m 1s");
});

test("buildStaticAnalysisProgressSummary matches the task management progress rules for grouped static scans", () => {
  const runningSummary = buildStaticAnalysisProgressSummary({
    opengrepTask: {
      id: "og-1",
      project_id: "project-1",
      status: "running",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:12:00.000Z",
    },
    gitleaksTask: {
      id: "gl-1",
      project_id: "project-1",
      status: "completed",
      created_at: "2026-03-12T07:00:30.000Z",
      updated_at: "2026-03-12T07:05:00.000Z",
    },
    nowMs: Date.parse("2026-03-12T07:12:00.000Z"),
  });

  assert.equal(runningSummary.progressPercent, 83);

  const completedSummary = buildStaticAnalysisProgressSummary({
    opengrepTask: {
      id: "og-2",
      project_id: "project-2",
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:10:00.000Z",
    },
    gitleaksTask: {
      id: "gl-2",
      project_id: "project-2",
      status: "completed",
      created_at: "2026-03-12T07:00:15.000Z",
      updated_at: "2026-03-12T07:04:00.000Z",
    },
    nowMs: Date.parse("2026-03-12T07:12:00.000Z"),
  });

  assert.equal(completedSummary.progressPercent, 100);
});

test("buildStaticAnalysisProgressSummary falls back to the primary task status when the group is neither running nor fully completed", () => {
  const failedSummary = buildStaticAnalysisProgressSummary({
    opengrepTask: null,
    gitleaksTask: {
      id: "gl-only",
      project_id: "project-3",
      status: "failed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:00.000Z",
    },
    nowMs: Date.parse("2026-03-12T07:05:00.000Z"),
  });

  assert.equal(failedSummary.progressPercent, 100);
});

test("buildStaticAnalysisProgressSummary keeps the management-page primary task precedence for mixed static engine states", () => {
  const summary = buildStaticAnalysisProgressSummary({
    opengrepTask: {
      id: "og-primary",
      project_id: "project-4",
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:08:00.000Z",
    },
    gitleaksTask: {
      id: "gl-secondary",
      project_id: "project-4",
      status: "running",
      created_at: "2026-03-12T07:00:20.000Z",
      updated_at: "2026-03-12T07:12:00.000Z",
    },
    nowMs: Date.parse("2026-03-12T07:12:00.000Z"),
  });

  assert.equal(summary.progressPercent, 100);
});
