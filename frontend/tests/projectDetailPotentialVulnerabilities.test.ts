import test from "node:test";
import assert from "node:assert/strict";

import { buildProjectDetailPotentialTree } from "../src/pages/project-detail/potentialVulnerabilities.ts";

test("buildProjectDetailPotentialTree 保留中高置信度且中危以上漏洞并取消 top10 截断", () => {
	const result = buildProjectDetailPotentialTree({
		projectName: "demo",
		agentTasks: [
			{
				id: "agent-new",
				project_id: "project-1",
				name: "最新智能扫描",
				description: "intelligent",
				created_at: "2026-03-19T10:00:00Z",
			},
			{
				id: "agent-old",
				project_id: "project-1",
				name: "旧智能扫描",
				description: "intelligent",
				created_at: "2026-03-18T10:00:00Z",
			},
		] as any,
		opengrepTasks: [
			{
				id: "static-1",
				project_id: "project-1",
				name: "静态扫描任务",
				created_at: "2026-03-17T10:00:00Z",
			},
		] as any,
		agentFindings: [
			...Array.from({ length: 11 }, (_, index) => ({
				id: `agent-finding-${index + 1}`,
				task_id: "agent-new",
				vulnerability_type: "SQL Injection",
				severity: "high",
				title: `智能漏洞 ${index + 1}`,
				display_title: `智能漏洞 ${index + 1}`,
				description: "desc",
				file_path: `/tmp/work/demo/src/api/auth.ts`,
				line_start: index + 1,
				line_end: index + 1,
				context_start_line: index + 1,
				context_end_line: index + 1,
				status: "open",
				is_verified: true,
				has_poc: false,
				suggestion: null,
				fix_code: null,
				ai_explanation: null,
				ai_confidence: 0.92,
				confidence: 0.92,
				created_at: "2026-03-19T10:00:00Z",
			})),
			{
				id: "agent-medium-confidence",
				task_id: "agent-new",
				vulnerability_type: "IDOR",
				severity: "medium",
				title: "中危中置信漏洞",
				display_title: "中危中置信漏洞",
				description: "desc",
				file_path: `/tmp/work/demo/src/api/auth.ts`,
				line_start: 120,
				line_end: 120,
				context_start_line: 120,
				context_end_line: 120,
				status: "open",
				is_verified: true,
				has_poc: false,
				suggestion: null,
				fix_code: null,
				ai_explanation: null,
				ai_confidence: 0.65,
				confidence: 0.65,
				created_at: "2026-03-19T10:00:00Z",
			},
			{
				id: "agent-filtered-low-confidence",
				task_id: "agent-new",
				vulnerability_type: "XSS",
				severity: "critical",
				title: "低置信度漏洞",
				display_title: "低置信度漏洞",
				description: "desc",
				file_path: `/tmp/work/demo/src/api/auth.ts`,
				line_start: 140,
				line_end: 140,
				context_start_line: 140,
				context_end_line: 140,
				status: "open",
				is_verified: true,
				has_poc: false,
				suggestion: null,
				fix_code: null,
				ai_explanation: null,
				ai_confidence: 0.49,
				confidence: 0.49,
				created_at: "2026-03-19T10:00:00Z",
			},
			{
				id: "agent-filtered-low-severity",
				task_id: "agent-old",
				vulnerability_type: "Info Leak",
				severity: "low",
				title: "低危漏洞",
				display_title: "低危漏洞",
				description: "desc",
				file_path: `/tmp/work/demo/src/api/legacy.ts`,
				line_start: 8,
				line_end: 8,
				context_start_line: 8,
				context_end_line: 8,
				status: "open",
				is_verified: true,
				has_poc: false,
				suggestion: null,
				fix_code: null,
				ai_explanation: null,
				ai_confidence: 0.96,
				confidence: 0.96,
				created_at: "2026-03-18T10:00:00Z",
			},
		] as any,
		opengrepFindings: [
			{
				id: "static-medium",
				scan_task_id: "static-1",
				rule: {},
				rule_name: "路径遍历",
				cwe: ["CWE-22"],
				description: "desc",
				file_path: "/workspace/demo/src/http/download.ts",
				start_line: 33,
				severity: "WARNING",
				status: "open",
				confidence: "MEDIUM",
			},
			{
				id: "static-filtered-low-confidence",
				scan_task_id: "static-1",
				rule: {},
				rule_name: "命令注入",
				cwe: ["CWE-78"],
				description: "desc",
				file_path: "/workspace/demo/src/http/shell.ts",
				start_line: 41,
				severity: "ERROR",
				status: "open",
				confidence: "LOW",
			},
		] as any,
	});

	assert.equal(result.totalFindings, 13);
	assert.equal(result.tasks.length, 2);
	assert.equal(result.tasks[0]?.taskId, "agent-new");
	assert.equal(result.tasks[1]?.taskId, "static-1");

	const srcDirectory = result.tasks[0]?.children[0];
	assert.equal(srcDirectory?.type, "directory");
	assert.equal(srcDirectory?.name, "src");

	const apiDirectory =
		srcDirectory?.type === "directory" ? srcDirectory.children[0] : null;
	assert.equal(apiDirectory?.type, "directory");
	assert.equal(apiDirectory?.name, "api");

	const authFile =
		apiDirectory?.type === "directory" ? apiDirectory.children[0] : null;
	assert.equal(authFile?.type, "file");
	assert.equal(authFile?.name, "auth.ts");
	assert.equal(authFile?.count, 12);

	const findingTitles =
		authFile?.type === "file"
			? authFile.children.map((item) => item.title)
			: [];
	assert.equal(findingTitles.length, 12);
	assert.equal(findingTitles[0], "智能漏洞 1");
	assert.equal(findingTitles[10], "智能漏洞 11");
	assert.equal(findingTitles[11], "中危中置信漏洞");
	assert.ok(!findingTitles.includes("低置信度漏洞"));
	assert.ok(!findingTitles.includes("低危漏洞"));
});

test("buildProjectDetailPotentialTree 按任务时间倒序并保留静态扫描的中危中置信漏洞", () => {
	const result = buildProjectDetailPotentialTree({
		projectName: "demo",
		agentTasks: [
			{
				id: "agent-1",
				project_id: "project-1",
				name: "智能扫描任务",
				description: "intelligent",
				created_at: "2026-03-18T08:00:00Z",
			},
		] as any,
		opengrepTasks: [
			{
				id: "static-2",
				project_id: "project-1",
				name: "静态扫描任务",
				created_at: "2026-03-19T08:00:00Z",
			},
		] as any,
		agentFindings: [
			{
				id: "agent-one",
				task_id: "agent-1",
				vulnerability_type: "SQL Injection",
				severity: "high",
				title: "智能扫描漏洞",
				display_title: "智能扫描漏洞",
				description: "desc",
				file_path: `/tmp/work/demo/src/service/auth.ts`,
				line_start: 18,
				line_end: 18,
				context_start_line: 18,
				context_end_line: 18,
				status: "open",
				is_verified: true,
				has_poc: false,
				suggestion: null,
				fix_code: null,
				ai_explanation: null,
				ai_confidence: 0.95,
				confidence: 0.95,
				created_at: "2026-03-18T08:00:00Z",
			},
		] as any,
		opengrepFindings: [
			{
				id: "static-one",
				scan_task_id: "static-2",
				rule: {},
				rule_name: "路径遍历",
				cwe: ["CWE-22"],
				description: "desc",
				file_path: "/workspace/demo/src/http/download.ts",
				start_line: 33,
				severity: "WARNING",
				status: "open",
				confidence: "MEDIUM",
			},
		] as any,
	});

	assert.equal(result.tasks[0]?.taskId, "static-2");
	assert.equal(result.tasks[0]?.taskCategory, "static");
	assert.equal(result.tasks[0]?.count, 1);
	const staticSrcDirectory = result.tasks[0]?.children[0];
	assert.equal(staticSrcDirectory?.type, "directory");
	assert.equal(staticSrcDirectory?.name, "src");
});
