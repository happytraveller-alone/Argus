import test from "node:test";
import assert from "node:assert/strict";

import {
	getProjectCardPotentialVulnerabilities,
	getProjectCardRecentTasks,
	getProjectCardSummaryStats,
	getProjectFoundIssuesBreakdown,
} from "../src/features/projects/services/projectCardPreview.ts";

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
	] as any;

	const breakdown = getProjectFoundIssuesBreakdown({
		projectId: "project-1",
		agentTasks,
		opengrepTasks: [] as any,
	});
	assert.equal(breakdown.intelligentIssues, 0);
	assert.equal(breakdown.totalIssues, 0);

	const recentTasks = getProjectCardRecentTasks({
		projectId: "project-1",
		agentTasks,
		opengrepTasks: [] as any,
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
		] as any,
		agentTaskCategoryMap: {
			"agent-legacy": "intelligent",
		},
	});
	assert.equal(potential[0]?.taskCategory, "intelligent");
});

test("projectCardPreview 仅保留 opengrep 静态审计路由契约", () => {
	const recentTasks = getProjectCardRecentTasks({
		projectId: "project-1",
		agentTasks: [] as any,
		opengrepTasks: [
			{
				id: "opengrep-1",
				project_id: "project-1",
				status: "completed",
				created_at: "2026-03-16T00:00:00Z",
				updated_at: "2026-03-16T00:03:00Z",
				total_findings: 5,
				scan_duration_ms: 180000,
				files_scanned: 8,
				lines_scanned: 256,
				high_confidence_count: 3,
			},
		] as any,
	});

	assert.equal(recentTasks.length, 1);
	assert.equal(
		recentTasks[0]?.route,
		"/static-analysis/opengrep-1?opengrepTaskId=opengrep-1",
	);
	assert.equal(recentTasks[0]?.vulnerabilities, 5);
	assert.equal(recentTasks[0]?.taskCategory, "static");
});

test("projectCardPreview aggregates static issue breakdown from visible opengrep severity buckets", () => {
	const breakdown = getProjectFoundIssuesBreakdown({
		projectId: "project-1",
		agentTasks: [] as any,
		opengrepTasks: [
			{
				id: "opengrep-buckets",
				project_id: "project-1",
				status: "completed",
				total_findings: 3,
				critical_count: 0,
				high_count: 1,
				medium_count: 1,
				low_count: 1,
				error_count: 3,
				warning_count: 0,
			},
		] as any,
	});

	assert.equal(breakdown.staticIssues, 3);
	assert.equal(breakdown.totalIssues, 3);

	const summary = getProjectCardSummaryStats({
		projectId: "project-1",
		agentTasks: [] as any,
		opengrepTasks: [
			{
				id: "opengrep-buckets",
				project_id: "project-1",
				status: "completed",
				total_findings: 3,
				critical_count: 0,
				high_count: 1,
				medium_count: 1,
				low_count: 1,
				error_count: 3,
				warning_count: 0,
			},
		] as any,
	});

	assert.deepEqual(summary.severityBreakdown, {
		critical: 0,
		high: 1,
		medium: 1,
		low: 1,
		total: 3,
	});
});
