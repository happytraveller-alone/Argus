import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import * as viewModel from "../src/pages/static-analysis/viewModel.ts";
import {
  buildStaticAnalysisListState,
  buildStaticAnalysisProgressSummary,
  buildStaticAnalysisTaskStatusSummary,
  buildCodeqlExplorationTimelineRows,
  buildUnifiedFindingRows,
  formatStaticAnalysisDuration,
  resolveStaticAnalysisDetailTaskIds,
} from "../src/pages/static-analysis/viewModel.ts";

const staticAnalysisPageSource = readFileSync(
  "src/pages/StaticAnalysis.tsx",
  "utf8",
);

test("buildUnifiedFindingRows normalizes opengrep, codeql and joern rows", () => {
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
    joernFindings: [
      {
        id: "jn-1",
        scan_task_id: "task-jn",
        severity: "ERROR",
        confidence: "HIGH",
        file_path: "/scan/project/src/bplist.c",
        start_line: 288,
        status: "open",
        rule: { check_id: "joern-c-buffer-overflow-libplist-cve-2017-6439" },
      },
    ],
    joernTaskId: "task-jn",
  });

  assert.equal(rows.length, 3);
  assert.equal(rows[0]?.engine, "opengrep");
  assert.equal(rows[0]?.rule, "auth-rule");
  assert.equal(rows[0]?.filePath, "repo/src/auth.ts");
  assert.equal(rows[0]?.severity, "MEDIUM");
  assert.equal(rows[0]?.confidence, "LOW");
  assert.equal(rows[1]?.engine, "codeql");
  assert.equal(rows[1]?.taskId, "task-cq");
  assert.equal(rows[1]?.rule, "cpp/sql-injection");
  assert.equal(rows[1]?.filePath, "src/main.cpp");
  assert.equal(rows[2]?.engine, "joern");
  assert.equal(rows[2]?.taskId, "task-jn");
  assert.equal(rows[2]?.rule, "joern-c-buffer-overflow-libplist-cve-2017-6439");
  assert.equal(rows[2]?.filePath, "src/bplist.c");
});

test("resolveStaticAnalysisDetailTaskIds treats engine as a table filter, not a CodeQL detail selector", () => {
  assert.deepEqual(
    resolveStaticAnalysisDetailTaskIds({
      taskId: "og-1",
      searchParams: new URLSearchParams("engine=codeql"),
    }),
    { opengrepTaskId: "og-1", codeqlTaskId: "", joernTaskId: "" },
  );
  assert.deepEqual(
    resolveStaticAnalysisDetailTaskIds({
      taskId: "og-1",
      searchParams: new URLSearchParams("opengrepTaskId=og-2&engine=codeql"),
    }),
    { opengrepTaskId: "og-2", codeqlTaskId: "", joernTaskId: "" },
  );
  assert.deepEqual(
    resolveStaticAnalysisDetailTaskIds({
      taskId: "cq-1",
      searchParams: new URLSearchParams("codeqlTaskId=cq-2&engine=codeql"),
    }),
    { opengrepTaskId: "", codeqlTaskId: "cq-2", joernTaskId: "" },
  );
  assert.deepEqual(
    resolveStaticAnalysisDetailTaskIds({
      taskId: "jn-1",
      searchParams: new URLSearchParams("joernTaskId=jn-2&engine=joern"),
    }),
    { opengrepTaskId: "", codeqlTaskId: "", joernTaskId: "jn-2" },
  );
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

test("buildStaticAnalysisListState filters, sorts and paginates static engine rows", () => {
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
      dismissalCategory: null,
      dismissalEvidence: null,
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
      dismissalCategory: null,
      dismissalEvidence: null,
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
      dismissalCategory: null,
      dismissalEvidence: null,
    },
    {
      key: "d",
      id: "d",
      taskId: "3",
      engine: "joern",
      rule: "rule-d",
      filePath: "src/bplist.c",
      line: 288,
      severity: "CRITICAL",
      severityScore: 4,
      confidence: "HIGH",
      confidenceScore: 3,
      status: "open",
      dismissalCategory: null,
      dismissalEvidence: null,
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

  assert.equal(state.totalRows, 4);
  assert.equal(state.totalPages, 2);
  assert.deepEqual(
    state.pagedRows.map((row) => row.key),
    ["d", "b"],
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

  const joernFiltered = buildStaticAnalysisListState({
    rows: [...rows],
    engineFilter: "joern",
    statusFilter: "open",
    severityFilter: "CRITICAL",
    confidenceFilter: "HIGH",
    page: 1,
    pageSize: 10,
  });

  assert.deepEqual(
    joernFiltered.pagedRows.map((row) => row.key),
    ["d"],
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

test("getStaticAnalysisTotalDisplayDurationMs sums static engine durations", () => {
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
    joernTask: {
      id: "jn-completed",
      project_id: "project-4",
      status: "completed",
      created_at: "2026-03-12T07:00:00.000Z",
      updated_at: "2026-03-12T07:00:10.000Z",
      scan_duration_ms: 10_000,
    },
    nowMs: Date.parse("2026-03-12T07:01:30.000Z"),
  });

  assert.equal(duration, 165_000);
});

test("buildStaticAnalysisProgressSummary follows grouped static engine status", () => {
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
    joernTask: {
      id: "jn-1",
      project_id: "project-1",
      status: "completed",
      created_at: "2026-03-12T07:00:45.000Z",
      updated_at: "2026-03-12T07:03:00.000Z",
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
    joernTask: {
      id: "jn-2",
      project_id: "project-2",
      status: "completed",
      created_at: "2026-03-12T07:00:20.000Z",
      updated_at: "2026-03-12T07:03:00.000Z",
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

test("buildStaticAnalysisHeaderSummary exposes Opengrep scan scheme label", () => {
	const baseTask = {
		id: "og-1",
		project_id: "project-1",
		project_name: "Demo",
		status: "completed",
		created_at: "2026-05-01T00:00:00Z",
		updated_at: "2026-05-01T00:00:02Z",
		scan_duration_ms: 2000,
		total_findings: 1,
	};

	assert.equal(
		viewModel.buildStaticAnalysisHeaderSummary({
			opengrepTask: { ...baseTask, opengrep_sandbox: "dockerfile_container" },
			codeqlTask: null,
			enabledEngines: ["opengrep"],
		}).scanSchemeLabel,
		"Podman 容器方案",
	);
	assert.equal(
		viewModel.buildStaticAnalysisHeaderSummary({
			opengrepTask: { ...baseTask, opengrep_sandbox: "unknown" as unknown as "a3s_box" },
			codeqlTask: null,
			enabledEngines: ["opengrep"],
		}).scanSchemeLabel,
		"Podman 容器方案",
	);
	assert.equal(
		viewModel.buildStaticAnalysisHeaderSummary({
			opengrepTask: { ...baseTask, opengrep_sandbox: "a3s_box" },
			codeqlTask: null,
			enabledEngines: ["opengrep"],
		}).scanSchemeLabel,
		"A3S 沙箱方案",
	);
	assert.equal(
		viewModel.buildStaticAnalysisHeaderSummary({
			opengrepTask: null,
			codeqlTask: null,
			joernTask: { ...baseTask, id: "jn-1" },
			enabledEngines: ["joern"],
		}).scanSchemeLabel,
		"Joern CPG 方案",
	);
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

test("StaticAnalysis page uses backend task project names for the display fallback", () => {
  assert.doesNotMatch(staticAnalysisPageSource, /getProjectById/);
  assert.match(
    staticAnalysisPageSource,
    /opengrepTask\?\.project_name \|\| codeqlTask\?\.project_name \|\| joernTask\?\.project_name/,
  );
  assert.match(staticAnalysisPageSource, /staticProjectName/);
  assert.match(staticAnalysisPageSource, /fallbackProjectName/);
  assert.match(staticAnalysisPageSource, /codeqlTaskId/);
  assert.match(staticAnalysisPageSource, /joernTaskId/);
});

test("buildCodeqlExplorationTimelineRows exposes CodeQL evidence and redaction state", () => {
  const rows = buildCodeqlExplorationTimelineRows([
    {
      timestamp: "2026-05-02T00:00:00Z",
      event_type: "plan_reuse",
      stage: "build_plan_reused",
      progress: 34,
      redaction: { applied: false },
      payload: {
        reuse_reason: "accepted project-level sticky build plan exists",
        commands: ["make -j2"],
      },
    },
    {
      timestamp: "2026-05-02T00:00:01Z",
      event_type: "sandbox_command",
      stage: "sandbox_command_completed",
      progress: 38,
      redaction: { applied: true, patterns: ["api_key"] },
      payload: {
        command: "make -j2",
        stdout: "api_key=[REDACTED]",
        stderr: "compile failed",
        exit_code: 2,
        failure_category: "compile_error",
        dependency_installation: { detected: false },
      },
    },
  ]);

  assert.equal(rows.length, 2);
  assert.equal(rows[0]?.label, "复用构建方案");
  assert.equal(rows[0]?.reuseReason, "accepted project-level sticky build plan exists");
  assert.equal(rows[1]?.label, "沙箱命令");
  assert.equal(rows[1]?.command, "make -j2");
  assert.equal(rows[1]?.exitCode, 2);
  assert.equal(rows[1]?.failureCategory, "compile_error");
  assert.equal(rows[1]?.redacted, true);
  assert.match(rows[1]?.stdout || "", /\[REDACTED\]/);
});
