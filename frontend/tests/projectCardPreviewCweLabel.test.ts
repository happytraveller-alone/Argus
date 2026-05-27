import assert from "node:assert/strict";
import test from "node:test";

import {
	getProjectCardPotentialVulnerabilities,
	getProjectCardRecentTasks,
	getProjectCardSummaryStats,
	getProjectFoundIssuesBreakdown,
} from "../src/features/projects/services/projectCardPreview.ts";
import type { AgentFinding, AgentTask } from "../src/shared/api/agentTasks.ts";
import type {
	IntelligentTaskFinding,
	IntelligentTaskRecord,
} from "../src/shared/api/intelligentTasks.ts";
import type { OpengrepScanTask } from "../src/shared/api/opengrep.ts";

function scanTask(
	id: string,
	engine: "opengrep" | "codeql" | "joern",
	createdAt: string,
	totalFindings: number,
): OpengrepScanTask {
	return {
		id,
		engine,
		project_id: "project-1",
		name: `${engine} scan`,
		status: "completed",
		target_path: ".",
		total_findings: totalFindings,
		error_count: 0,
		warning_count: 0,
		scan_duration_ms: 0,
		files_scanned: 0,
		lines_scanned: 0,
		created_at: createdAt,
	};
}

function intelligentFinding(id: string): IntelligentTaskFinding {
	return {
		id,
		severity: "high",
		summary: "finding",
		evidence: "evidence",
	};
}

test("projectCardPreview 为潜在漏洞展示 编号+中文 的 CWE 文案", () => {
	const items = getProjectCardPotentialVulnerabilities({
		verifiedAgentFindings: [
			{
				id: "agent-1",
				task_id: "task-1",
				cwe_id: "CWE-89",
				severity: "high",
				ai_confidence: 0.96,
				confidence: 0.96,
				file_path: "src/api/user.ts",
				line_start: 18,
				created_at: "2026-03-15T00:00:00Z",
				title: "SQL 注入",
				display_title: "SQL 注入",
				vulnerability_type: "SQL Injection",
			},
		] as unknown as Parameters<
			typeof getProjectCardPotentialVulnerabilities
		>[0]["verifiedAgentFindings"],
		limit: 1,
	});

	assert.equal(items.length, 1);
	assert.equal(items[0]?.cweLabel, "CWE-89 SQL注入");
});

test("projectCardPreview ignores retired legacy agent tasks in summary and recent state", () => {
	const agentTasks = [
		{
			id: "agent-legacy",
			project_id: "project-1",
			name: "历史智能审计-Demo",
			description: "历史迁移前任务",
			status: "completed",
			created_at: "2026-03-15T00:00:00Z",
			started_at: "2026-03-15T00:01:00Z",
			completed_at: "2026-03-15T00:05:00Z",
			progress_percentage: 100,
			total_files: 12,
			analyzed_files: 12,
			verified_count: 3,
			critical_count: 1,
			high_count: 1,
			medium_count: 1,
			low_count: 0,
		},
	] satisfies AgentTask[];

	const breakdown = getProjectFoundIssuesBreakdown({
		projectId: "project-1",
		agentTasks,
		opengrepTasks: [],
	});
	assert.equal(breakdown.intelligentIssues, 0);
	assert.equal(breakdown.totalIssues, 0);

	const recentTasks = getProjectCardRecentTasks({
		projectId: "project-1",
		agentTasks,
		opengrepTasks: [],
	});
	assert.deepEqual(recentTasks, []);

	const potential = getProjectCardPotentialVulnerabilities({
		verifiedAgentFindings: [
			{
				id: "finding-1",
				task_id: "agent-legacy",
				severity: "high",
				ai_confidence: 0.95,
				confidence: 0.95,
				file_path: "src/api/user.ts",
				line_start: 18,
				created_at: "2026-03-15T00:00:00Z",
				title: "SQL 注入",
				display_title: "SQL 注入",
				vulnerability_type: "SQL Injection",
			},
		] satisfies AgentFinding[],
		agentTaskCategoryMap: {
			"agent-legacy": "intelligent",
		},
	});
	assert.equal(potential[0]?.taskCategory, "intelligent");
});

test("projectCardPreview 仅保留 opengrep 静态审计路由契约", () => {
	const recentTasks = getProjectCardRecentTasks({
		projectId: "project-1",
		agentTasks: [],
		opengrepTasks: [
			{
				id: "opengrep-1",
				project_id: "project-1",
				name: "Opengrep Scan",
				status: "completed",
				target_path: ".",
				created_at: "2026-03-16T00:00:00Z",
				updated_at: "2026-03-16T00:03:00Z",
				total_findings: 5,
				error_count: 0,
				warning_count: 0,
				scan_duration_ms: 180000,
				files_scanned: 8,
				lines_scanned: 256,
				high_confidence_count: 3,
			},
		] satisfies OpengrepScanTask[],
	});

	assert.equal(recentTasks.length, 1);
	assert.equal(
		recentTasks[0]?.route,
		"/static-analysis/opengrep-1?opengrepTaskId=opengrep-1",
	);
	assert.equal(recentTasks[0]?.vulnerabilities, 5);
	assert.equal(recentTasks[0]?.taskCategory, "static");
});

test("projectCardPreview 在项目详情最近任务中包含所有静态引擎和智能审计任务", () => {
	const recentTasks = getProjectCardRecentTasks({
		projectId: "project-1",
		agentTasks: [],
		opengrepTasks: [
			scanTask("opengrep-1", "opengrep", "2026-03-16T00:00:00Z", 2),
		],
		codeqlTasks: [scanTask("codeql-1", "codeql", "2026-03-17T00:00:00Z", 3)],
		joernTasks: [scanTask("joern-1", "joern", "2026-03-18T00:00:00Z", 4)],
		intelligentTasks: [
			{
				taskId: "intel-1",
				projectId: "project-1",
				status: "completed",
				createdAt: "2026-03-19T00:00:00Z",
				llmModel: "gpt-test",
				llmFingerprint: "fp-test",
				inputSummary: "",
				eventLog: [],
				reportSummary: "",
				findings: [
					intelligentFinding("finding-1"),
					intelligentFinding("finding-2"),
				],
			},
		] satisfies IntelligentTaskRecord[],
		limit: 10,
	});

	assert.deepEqual(
		recentTasks.map((task) => task.id),
		["intel-1", "joern-1", "codeql-1", "opengrep-1"],
	);
	assert.equal(recentTasks[0]?.scanTypeLabel, "智能审计");
	assert.equal(
		recentTasks[1]?.route,
		"/static-analysis/joern-1?joernTaskId=joern-1&engine=joern",
	);
	assert.equal(
		recentTasks[2]?.route,
		"/codeql-analysis/codeql-1?codeqlTaskId=codeql-1&engine=codeql",
	);
	assert.equal(recentTasks[3]?.vulnerabilities, 2);
});

test("projectCardPreview aggregates static issue breakdown from visible opengrep severity buckets", () => {
	const breakdown = getProjectFoundIssuesBreakdown({
		projectId: "project-1",
		agentTasks: [],
		opengrepTasks: [
			{
				id: "opengrep-buckets",
				project_id: "project-1",
				name: "Opengrep Buckets",
				status: "completed",
				target_path: ".",
				total_findings: 3,
				critical_count: 0,
				high_count: 1,
				medium_count: 1,
				low_count: 1,
				error_count: 3,
				warning_count: 0,
				scan_duration_ms: 0,
				files_scanned: 0,
				lines_scanned: 0,
				created_at: "2026-03-16T00:00:00Z",
			},
		] satisfies OpengrepScanTask[],
	});

	assert.equal(breakdown.staticIssues, 3);
	assert.equal(breakdown.totalIssues, 3);

	const summary = getProjectCardSummaryStats({
		projectId: "project-1",
		agentTasks: [],
		opengrepTasks: [
			{
				id: "opengrep-buckets",
				project_id: "project-1",
				name: "Opengrep Buckets",
				status: "completed",
				target_path: ".",
				total_findings: 3,
				critical_count: 0,
				high_count: 1,
				medium_count: 1,
				low_count: 1,
				error_count: 3,
				warning_count: 0,
				scan_duration_ms: 0,
				files_scanned: 0,
				lines_scanned: 0,
				created_at: "2026-03-16T00:00:00Z",
			},
		] satisfies OpengrepScanTask[],
	});

	assert.deepEqual(summary.severityBreakdown, {
		critical: 0,
		high: 1,
		medium: 1,
		low: 1,
		total: 3,
	});
});
