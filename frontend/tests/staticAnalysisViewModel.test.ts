import test from "node:test";
import assert from "node:assert/strict";

import * as viewModel from "../src/pages/static-analysis/viewModel.ts";
import {
  buildStaticAnalysisProgressSummary,
  buildStaticAnalysisTaskStatusSummary,
  buildStaticAnalysisListState,
  buildUnifiedFindingRows,
  formatStaticAnalysisDuration,
} from "../src/pages/static-analysis/viewModel.ts";

test("buildUnifiedFindingRows normalizes opengrep rows only", () => {
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
      {
        id: "og-hidden",
        scan_task_id: "task-og",
        severity: "LOW",
        confidence: "HIGH",
        file_path: "src/ignored.ts",
        start_line: 4,
        status: "open",
        rule_name: "ignored-rule",
      },
    ],
    opengrepTaskId: "task-og",
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.engine, "opengrep");
  assert.equal(rows[0]?.filePath, "repo/src/auth.ts");
  assert.equal(rows[0]?.severity, "MEDIUM");
  assert.equal(rows[0]?.confidence, "LOW");
});

test("static analysis finding status helpers expose tri-state labels and tones", () => {
  assert.equal(viewModel.getStaticAnalysisFindingStatusLabel("open"), "待验证");
  assert.equal(viewModel.getStaticAnalysisFindingStatusLabel("verified"), "确报");
  assert.equal(viewModel.getStaticAnalysisFindingStatusLabel("false_positive"), "误报");

  assert.match(
    viewModel.getStaticAnalysisFindingStatusBadgeClass("open"),
    /bg-muted/,
  );
  assert.match(
    viewModel.getStaticAnalysisFindingStatusBadgeClass("verified"),
    /emerald/,
  );
  assert.match(
    viewModel.getStaticAnalysisFindingStatusBadgeClass("false_positive"),
    /rose/,
  );
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
    severityFilter: "all",
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
    severityFilter: "all",
    confidenceFilter: "HIGH",
    page: 1,
    pageSize: 10,
  });

  assert.deepEqual(
    filtered.pagedRows.map((row) => row.key),
    ["b"],
  );
});

test("buildStaticAnalysisListState applies severityFilter across unified engine rows", () => {
  const rows = [
    {
      key: "og-high",
      id: "og-high",
      taskId: "task-og",
      engine: "opengrep",
      rule: "rule-og",
      filePath: "src/auth.ts",
      line: 12,
      severity: "HIGH",
      severityScore: 3,
      confidence: "HIGH",
      confidenceScore: 3,
      status: "open",
    },
    {
      key: "gl-low",
      id: "gl-low",
      taskId: "task-gl",
      engine: "gitleaks",
      rule: "rule-gl",
      filePath: "secrets.env",
      line: 5,
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
    severityFilter: "HIGH",
    confidenceFilter: "all",
    page: 1,
    pageSize: 10,
  });

  assert.deepEqual(
    state.pagedRows.map((row) => row.key),
    ["og-high"],
  );
});

test("buildStaticAnalysisListState applies confidenceFilter to gitleaks rows too", () => {
  const rows = [
    {
      key: "og-high",
      id: "og-high",
      taskId: "task-og",
      engine: "opengrep",
      rule: "rule-og",
      filePath: "src/auth.ts",
      line: 12,
      severity: "HIGH",
      severityScore: 3,
      confidence: "HIGH",
      confidenceScore: 3,
      status: "open",
    },
    {
      key: "gl-medium",
      id: "gl-medium",
      taskId: "task-gl",
      engine: "gitleaks",
      rule: "rule-gl",
      filePath: "secrets.env",
      line: 5,
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
    severityFilter: "all",
    confidenceFilter: "HIGH",
    page: 1,
    pageSize: 10,
  });

  assert.deepEqual(
    state.pagedRows.map((row) => row.key),
    ["og-high"],
  );
});

test("formatStaticAnalysisDuration formats milliseconds into readable labels", () => {
  assert.equal(formatStaticAnalysisDuration(12), "12 ms");
  assert.equal(formatStaticAnalysisDuration(1200), "00:00:01");
  assert.equal(formatStaticAnalysisDuration(61_000), "00:01:01");
});

test("getStaticAnalysisTaskDisplayDurationMs uses elapsed time for running tasks when backend duration is stale", () => {
  const duration = viewModel.getStaticAnalysisTaskDisplayDurationMs?.(
    {
      id: "og-running",
      project_id: "project-1",
      status: "running",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:00:10.000Z",
      scan_duration_ms: 0,
    },
    Date.parse("2026-03-12T07:01:30.000Z"),
  );

  assert.equal(duration, 90_000);
});

test("getStaticAnalysisTaskDisplayDurationMs does not move backwards when backend duration is ahead of elapsed time", () => {
  const duration = viewModel.getStaticAnalysisTaskDisplayDurationMs?.(
    {
      id: "gl-running",
      project_id: "project-2",
      status: "running",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:00.000Z",
      scan_duration_ms: 120_000,
    },
    Date.parse("2026-03-12T07:01:50.000Z"),
  );

  assert.equal(duration, 120_000);
});

test("getStaticAnalysisTaskDisplayDurationMs falls back to updated_at for completed tasks without a persisted duration", () => {
  const duration = viewModel.getStaticAnalysisTaskDisplayDurationMs?.(
    {
      id: "ba-completed",
      project_id: "project-3",
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:00:45.000Z",
      scan_duration_ms: 0,
    },
    Date.parse("2026-03-12T07:05:00.000Z"),
  );

  assert.equal(duration, 45_000);
});

test("getStaticAnalysisTotalDisplayDurationMs sums completed and running engine durations", () => {
  const duration = viewModel.getStaticAnalysisTotalDisplayDurationMs?.({
    opengrepTask: {
      id: "og-completed",
      project_id: "project-4",
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:35.000Z",
      scan_duration_ms: 95_000,
    },
    gitleaksTask: {
      id: "gl-running",
      project_id: "project-4",
      status: "running",
      created_at: "2026-03-12T07:00:30.000Z",
      updated_at: "2026-03-12T07:00:40.000Z",
      scan_duration_ms: 0,
    },
    banditTask: null,
    phpstanTask: null,
    nowMs: Date.parse("2026-03-12T07:01:30.000Z"),
  });

  assert.equal(duration, 155_000);
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
    banditTask: null,
    phpstanTask: null,
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
    banditTask: null,
    phpstanTask: null,
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
    banditTask: null,
    phpstanTask: null,
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
    banditTask: null,
    phpstanTask: null,
    nowMs: Date.parse("2026-03-12T07:12:00.000Z"),
  });

  assert.equal(summary.progressPercent, 83);
});

test("buildStaticAnalysisTaskStatusSummary marks mixed completed and failed engines as failed", () => {
  const summary = buildStaticAnalysisTaskStatusSummary({
    opengrepTask: null,
    gitleaksTask: {
      id: "gl-1",
      project_id: "project-5",
      status: "completed",
      created_at: "2026-03-12T07:00:10.000Z",
      updated_at: "2026-03-12T07:02:00.000Z",
      total_findings: 0,
      scan_duration_ms: 0,
      files_scanned: 0,
    },
    banditTask: null,
    phpstanTask: null,
    pmdTask: {
      id: "pmd-1",
      project_id: "project-5",
      status: "failed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:00.000Z",
      error_message: "PMD process failed",
      total_findings: 0,
      scan_duration_ms: 0,
      files_scanned: 0,
    },
  });

  assert.equal(summary.aggregateStatus, "failed");
  assert.equal(summary.aggregateLabel, "任务失败");
  assert.equal(summary.progressHint, "扫描已结束，至少一个引擎失败");
  assert.deepEqual(summary.failureReasons, [
    {
      engine: "pmd",
      engineLabel: "PMD",
      isTimeout: false,
      message: "PMD process failed",
    },
  ]);
});

test("buildStaticAnalysisTaskStatusSummary falls back to diagnostics summary for PMD failures", () => {
  const summary = buildStaticAnalysisTaskStatusSummary({
    opengrepTask: null,
    gitleaksTask: null,
    banditTask: null,
    phpstanTask: null,
    pmdTask: {
      id: "pmd-2",
      project_id: "project-6",
      status: "failed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:00.000Z",
      diagnostics_summary: "rule-config parse failed at line 3",
      total_findings: 0,
      scan_duration_ms: 0,
      files_scanned: 0,
    },
  });

  assert.deepEqual(summary.failureReasons, [
    {
      engine: "pmd",
      engineLabel: "PMD",
      isTimeout: false,
      message: "rule-config parse failed at line 3",
    },
  ]);
});

test("buildStaticAnalysisTaskStatusSummary uses a generic fallback when a failed engine exposes no reason", () => {
  const summary = buildStaticAnalysisTaskStatusSummary({
    opengrepTask: {
      id: "og-1",
      project_id: "project-7",
      status: "failed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:00.000Z",
      total_findings: 0,
      error_count: 0,
      warning_count: 0,
      scan_duration_ms: 0,
      files_scanned: 0,
      lines_scanned: 0,
      name: "Opengrep",
      target_path: ".",
    } as any,
    gitleaksTask: null,
    banditTask: null,
    phpstanTask: null,
    pmdTask: null,
  });

  assert.deepEqual(summary.failureReasons, [
    {
      engine: "opengrep",
      engineLabel: "Opengrep",
      isTimeout: false,
      message: "任务已失败，请查看后端日志获取更多信息。",
    },
  ]);
});
