import test from "node:test";
import assert from "node:assert/strict";

import {
	buildProjectDetailPotentialTree,
	flattenProjectDetailPotentialFindings,
} from "../src/pages/project-detail/potentialVulnerabilities.ts";

function staticTask(id: string, created_at: string) {
	return {
		id,
		project_id: "project-1",
		name: "静态审计",
		created_at,
	} as any;
}

function staticFinding(params: {
	id: string;
	taskId: string;
	ruleName: string;
	filePath: string;
	line: number;
	severity: string;
	confidence: string;
}) {
	return {
		id: params.id,
		scan_task_id: params.taskId,
		rule: {},
		rule_name: params.ruleName,
		cwe: ["CWE-22"],
		description: "desc",
		file_path: params.filePath,
		start_line: params.line,
		severity: params.severity,
		status: "open",
		confidence: params.confidence,
	} as any;
}

test("buildProjectDetailPotentialTree 保留静态中高置信度且中危以上漏洞并取消 top10 截断", () => {
	const result = buildProjectDetailPotentialTree({
		projectName: "demo",
		opengrepTasks: [staticTask("static-1", "2026-03-17T10:00:00Z")],
		opengrepFindings: [
			...Array.from({ length: 11 }, (_, index) =>
				staticFinding({
					id: `static-finding-${index + 1}`,
					taskId: "static-1",
					ruleName: `静态漏洞 ${index + 1}`,
					filePath: "/workspace/demo/src/api/auth.ts",
					line: index + 1,
					severity: "ERROR",
					confidence: "HIGH",
				}),
			),
			staticFinding({
				id: "static-medium-confidence",
				taskId: "static-1",
				ruleName: "中危中置信漏洞",
				filePath: "/workspace/demo/src/api/auth.ts",
				line: 120,
				severity: "WARNING",
				confidence: "MEDIUM",
			}),
			staticFinding({
				id: "static-filtered-low-confidence",
				taskId: "static-1",
				ruleName: "低置信度漏洞",
				filePath: "/workspace/demo/src/api/auth.ts",
				line: 140,
				severity: "ERROR",
				confidence: "LOW",
			}),
			staticFinding({
				id: "static-filtered-low-severity",
				taskId: "static-1",
				ruleName: "低危漏洞",
				filePath: "/workspace/demo/src/api/legacy.ts",
				line: 8,
				severity: "INFO",
				confidence: "HIGH",
			}),
		],
	});

	assert.equal(result.totalFindings, 12);
	assert.equal(result.tasks.length, 1);
	assert.equal(result.tasks[0]?.taskId, "static-1");

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
		authFile?.type === "file" ? authFile.children.map((item) => item.title) : [];
	assert.equal(findingTitles.length, 12);
	assert.equal(findingTitles[0], "静态漏洞 1");
	assert.equal(findingTitles[10], "静态漏洞 11");
	assert.equal(findingTitles[11], "中危中置信漏洞");
	assert.ok(!findingTitles.includes("低置信度漏洞"));
	assert.ok(!findingTitles.includes("低危漏洞"));
});

test("buildProjectDetailPotentialTree 按任务时间倒序并保留静态审计的中危中置信漏洞", () => {
	const result = buildProjectDetailPotentialTree({
		projectName: "demo",
		opengrepTasks: [
			staticTask("static-old", "2026-03-18T08:00:00Z"),
			staticTask("static-new", "2026-03-19T08:00:00Z"),
		],
		opengrepFindings: [
			staticFinding({
				id: "static-one",
				taskId: "static-new",
				ruleName: "路径遍历",
				filePath: "/workspace/demo/src/http/download.ts",
				line: 33,
				severity: "WARNING",
				confidence: "MEDIUM",
			}),
			staticFinding({
				id: "static-two",
				taskId: "static-old",
				ruleName: "SQL 注入",
				filePath: "/workspace/demo/src/db.ts",
				line: 12,
				severity: "ERROR",
				confidence: "HIGH",
			}),
		],
	});

	assert.equal(result.tasks[0]?.taskId, "static-new");
	assert.equal(result.tasks[0]?.taskCategory, "static");
	assert.equal(result.tasks[0]?.count, 1);
	const staticSrcDirectory = result.tasks[0]?.children[0];
	assert.equal(staticSrcDirectory?.type, "directory");
	assert.equal(staticSrcDirectory?.name, "src");
});

test("flattenProjectDetailPotentialFindings 输出排序后的静态列表并保留任务元信息", () => {
	const tree = buildProjectDetailPotentialTree({
		projectName: "demo",
		opengrepTasks: [
			staticTask("static-critical-task", "2026-03-20T12:00:00Z"),
			staticTask("static-high-new-task", "2026-03-20T10:00:00Z"),
			staticTask("static-high-old-task", "2026-03-18T10:00:00Z"),
			staticTask("static-medium-task", "2026-03-19T08:00:00Z"),
		],
		opengrepFindings: [
			staticFinding({
				id: "static-critical",
				taskId: "static-critical-task",
				ruleName: "远程执行",
				filePath: "/workspace/demo/src/app.ts",
				line: 10,
				severity: "CRITICAL",
				confidence: "HIGH",
			}),
			staticFinding({
				id: "static-high-new",
				taskId: "static-high-new-task",
				ruleName: "SQL 注入 A",
				filePath: "/workspace/demo/src/db.ts",
				line: 22,
				severity: "ERROR",
				confidence: "HIGH",
			}),
			staticFinding({
				id: "static-high-old",
				taskId: "static-high-old-task",
				ruleName: "SQL 注入 B",
				filePath: "/workspace/demo/src/db.ts",
				line: 30,
				severity: "ERROR",
				confidence: "HIGH",
			}),
			staticFinding({
				id: "static-medium",
				taskId: "static-medium-task",
				ruleName: "路径遍历",
				filePath: "/workspace/demo/src/http/download.ts",
				line: 33,
				severity: "WARNING",
				confidence: "MEDIUM",
			}),
		],
	});

	const list = flattenProjectDetailPotentialFindings(tree);
	assert.equal(list.length, 4);
	assert.deepEqual(
		list.map((item) => item.id),
		["static-critical", "static-high-new", "static-high-old", "static-medium"],
	);
	assert.ok(list[0]?.taskLabel.length);
	assert.equal(list[0]?.taskCategory, "static");
	assert.equal(list[3]?.taskCategory, "static");
	assert.equal(list[3]?.taskLabel, "静态审计");
});
