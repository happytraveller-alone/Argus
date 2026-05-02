import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import * as viewModel from "../src/pages/static-analysis/viewModel.ts";
import {
  buildStaticAnalysisListState,
  buildStaticAnalysisProgressSummary,
  buildStaticAnalysisTaskStatusSummary,
  buildUnifiedFindingRows,
  formatStaticAnalysisDuration,
} from "../src/pages/static-analysis/viewModel.ts";

const staticAnalysisPageSource = readFileSync(
  "src/pages/StaticAnalysis.tsx",
  "utf8",
);

test("buildUnifiedFindingRows normalizes opengrep and codeql rows", () => {
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
        severity: "INFO",
        confidence: "HIGH",
        file_path: "src/ignored.ts",
        start_line: 4,
        status: "open",
        rule_name: "ignored-rule",
      },
    ],
    opengrepTaskId: "task-og",
    codeqlFindings: [
      {
        id: "cq-1",
        scan_task_id: "task-cq",
        severity: "CRITICAL",
        confidence: "HIGH",
        file_path: "/scan/project/src/main.cpp",
        start_line: 33,
        status: "open",
        rule: { check_id: "cpp/sql-injection" },
      },
    ],
    codeqlTaskId: "task-cq",
  });

  assert.equal(rows.length, 2);
  assert.equal(rows[0]?.engine, "opengrep");
  assert.equal(rows[0]?.rule, "auth-rule");
  assert.equal(rows[0]?.filePath, "repo/src/auth.ts");
  assert.equal(rows[0]?.severity, "MEDIUM");
  assert.equal(rows[0]?.confidence, "LOW");
  assert.equal(rows[1]?.engine, "codeql");
  assert.equal(rows[1]?.taskId, "task-cq");
  assert.equal(rows[1]?.rule, "cpp/sql-injection");
  assert.equal(rows[1]?.filePath, "src/main.cpp");
});

test("static analysis completion refresh gate only fires once per completed task", () => {
  assert.equal(
    viewModel.shouldRefreshStaticAnalysisResultsAfterCompletion({
      taskId: "task-og",
      status: "running",
      refreshedTaskId: null,
    }),
    false,
  );
  assert.equal(
    viewModel.shouldRefreshStaticAnalysisResultsAfterCompletion({
      taskId: "task-og",
      status: "completed",
      refreshedTaskId: null,
    }),
    true,
  );
  assert.equal(
    viewModel.shouldRefreshStaticAnalysisResultsAfterCompletion({
      taskId: "task-og",
      status: "completed",
      refreshedTaskId: "task-og",
    }),
    false,
  );
});

test("buildUnifiedFindingRows compacts opengrep internal check identifiers", () => {
  const rows = buildUnifiedFindingRows({
    opengrepFindings: [
      {
        id: "og-fallback",
        scan_task_id: "task-og",
        severity: "HIGH",
        confidence: "HIGH",
        file_path: "src/app.py",
        start_line: 12,
        status: "open",
        rule: {
          check_id: "opengrep-rules.internal.python.vuln-django-debug",
        },
      },
    ],
    opengrepTaskId: "task-og",
  });

  assert.equal(rows[0]?.rule, "vuln-django-debug");
});

test("static analysis finding status helpers expose tri-state labels and tones", () => {
  assert.equal(viewModel.getStaticAnalysisFindingStatusLabel("open"), "待验证");
  assert.equal(viewModel.getStaticAnalysisFindingStatusLabel("verified"), "确报");
  assert.equal(
    viewModel.getStaticAnalysisFindingStatusLabel("false_positive"),
    "误报",
  );
  assert.match(viewModel.getStaticAnalysisFindingStatusBadgeClass("open"), /bg-muted/);
  assert.match(
    viewModel.getStaticAnalysisFindingStatusBadgeClass("verified"),
    /emerald/,
  );
  assert.match(
    viewModel.getStaticAnalysisFindingStatusBadgeClass("false_positive"),
    /rose/,
  );
});

test("buildStaticAnalysisListState filters, sorts and paginates opengrep/codeql rows", () => {
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
      engine: "codeql",
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
    engineFilter: "codeql",
    statusFilter: "open",
    severityFilter: "LOW",
    confidenceFilter: "MEDIUM",
    page: 1,
    pageSize: 10,
  });

  assert.deepEqual(
    filtered.pagedRows.map((row) => row.key),
    ["c"],
  );
});

test("formatStaticAnalysisDuration formats milliseconds into readable labels", () => {
  assert.equal(formatStaticAnalysisDuration(12), "12 ms");
  assert.equal(formatStaticAnalysisDuration(1200), "00:00:01");
  assert.equal(formatStaticAnalysisDuration(61_000), "00:01:01");
});

test("getStaticAnalysisTaskDisplayDurationMs uses elapsed time for running tasks when backend duration is stale", () => {
  const duration = viewModel.getStaticAnalysisTaskDisplayDurationMs(
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

test("getStaticAnalysisTaskDisplayDurationMs falls back to updated_at for completed tasks without a persisted duration", () => {
  const duration = viewModel.getStaticAnalysisTaskDisplayDurationMs(
    {
      id: "cq-completed",
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

test("getStaticAnalysisTotalDisplayDurationMs sums opengrep and codeql durations", () => {
  const duration = viewModel.getStaticAnalysisTotalDisplayDurationMs({
    opengrepTask: {
      id: "og-completed",
      project_id: "project-4",
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:35.000Z",
      scan_duration_ms: 95_000,
    },
    codeqlTask: {
      id: "cq-running",
      project_id: "project-4",
      status: "running",
      created_at: "2026-03-12T07:00:30.000Z",
      updated_at: "2026-03-12T07:00:40.000Z",
      scan_duration_ms: 0,
    },
    nowMs: Date.parse("2026-03-12T07:01:30.000Z"),
  });

  assert.equal(duration, 155_000);
});

test("buildStaticAnalysisProgressSummary follows grouped opengrep/codeql status", () => {
  const runningSummary = buildStaticAnalysisProgressSummary({
    opengrepTask: {
      id: "og-1",
      project_id: "project-1",
      status: "running",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:12:00.000Z",
    },
    codeqlTask: {
      id: "cq-1",
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
    codeqlTask: {
      id: "cq-2",
      project_id: "project-2",
      status: "completed",
      created_at: "2026-03-12T07:00:15.000Z",
      updated_at: "2026-03-12T07:04:00.000Z",
    },
    nowMs: Date.parse("2026-03-12T07:12:00.000Z"),
  });

  assert.equal(completedSummary.progressPercent, 100);
});

test("buildStaticAnalysisTaskStatusSummary marks mixed completed and failed engines as failed", () => {
  const summary = buildStaticAnalysisTaskStatusSummary({
    opengrepTask: {
      id: "og-1",
      project_id: "project-5",
      status: "completed",
      created_at: "2026-03-12T07:00:10.000Z",
      updated_at: "2026-03-12T07:02:00.000Z",
      total_findings: 0,
      scan_duration_ms: 0,
      files_scanned: 0,
    },
    codeqlTask: {
      id: "cq-1",
      project_id: "project-5",
      status: "failed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:00.000Z",
      error_message: "CodeQL process failed",
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
      engine: "codeql",
      engineLabel: "CodeQL",
      isTimeout: false,
      message: "CodeQL process failed",
    },
  ]);
});

test("buildStaticAnalysisTaskStatusSummary falls back to diagnostics summary for CodeQL failures", () => {
  const summary = buildStaticAnalysisTaskStatusSummary({
    opengrepTask: null,
    codeqlTask: {
      id: "cq-2",
      project_id: "project-6",
      status: "failed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:00.000Z",
      diagnostics_summary: "database finalize failed",
      total_findings: 0,
      scan_duration_ms: 0,
      files_scanned: 0,
    },
  });

  assert.deepEqual(summary.failureReasons, [
    {
      engine: "codeql",
      engineLabel: "CodeQL",
      isTimeout: false,
      message: "database finalize failed",
    },
  ]);
});

test("buildStaticAnalysisHeaderSummary prefers resolved project name over project id fallback", () => {
  const summary = viewModel.buildStaticAnalysisHeaderSummary({
    opengrepTask: null,
    codeqlTask: {
      id: "cq-1",
      project_id: "project-uuid-1",
      project_name: "Resolved Project Name",
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:01:00.000Z",
      total_findings: 2,
      error_count: 0,
      warning_count: 0,
      scan_duration_ms: 1000,
      files_scanned: 1,
      lines_scanned: 10,
      name: "CodeQL",
      target_path: ".",
    } as any,
    enabledEngines: ["codeql"],
    fallbackProjectName: "project-uuid-1",
  });

  assert.equal(summary.projectName, "Resolved Project Name");
});

test("resolveStaticAnalysisProjectNameFallback applies task, lookup, id fallback order", () => {
  assert.equal(
    viewModel.resolveStaticAnalysisProjectNameFallback({
      taskProjectName: "Task Project",
      resolvedProjectName: "Lookup Project",
      projectId: "project-uuid-1",
    }),
    "Task Project",
  );
  assert.equal(
    viewModel.resolveStaticAnalysisProjectNameFallback({
      taskProjectName: null,
      resolvedProjectName: "Lookup Project",
      projectId: "project-uuid-1",
    }),
    "Lookup Project",
  );
  assert.equal(
    viewModel.resolveStaticAnalysisProjectNameFallback({
      taskProjectName: "",
      resolvedProjectName: "",
      projectId: "project-uuid-1",
    }),
    "project-uuid-1",
  );
});

test("StaticAnalysis page performs cancellable display-only project lookup for id fallback", () => {
  assert.match(staticAnalysisPageSource, /api as databaseApi/);
  assert.match(
    staticAnalysisPageSource,
    /databaseApi\.getProjectById\(staticProjectId\)/,
  );
  assert.match(staticAnalysisPageSource, /let cancelled = false/);
  assert.match(staticAnalysisPageSource, /if \(cancelled\) return/);
  assert.match(staticAnalysisPageSource, /current\?\.projectId === staticProjectId/);
  assert.match(staticAnalysisPageSource, /staticProjectName/);
  assert.match(staticAnalysisPageSource, /fallbackProjectName/);
  assert.match(staticAnalysisPageSource, /codeqlTaskId/);
});
