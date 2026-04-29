import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import Header from "../src/pages/AgentAudit/components/Header.tsx";
import type { AgentTask } from "../src/shared/api/agentTasks.ts";

globalThis.React = React;

const taskFixture = {
	id: "task-1",
	project_id: "project-1",
	name: "Demo task",
	description: null,
	task_type: "intelligent_audit",
	status: "running",
	current_phase: null,
	current_step: null,
	total_files: 0,
	indexed_files: 0,
	analyzed_files: 0,
	files_with_findings: 0,
	total_chunks: 0,
	findings_count: 0,
	verified_count: 0,
	false_positive_count: 0,
	total_iterations: 0,
	tool_calls_count: 0,
	tokens_used: 0,
	critical_count: 0,
	high_count: 0,
	medium_count: 0,
	low_count: 0,
	quality_score: 0,
	security_score: null,
	created_at: "2026-04-29T00:00:00.000Z",
	started_at: null,
	completed_at: null,
	progress_percentage: 0,
	audit_scope: null,
	target_vulnerabilities: null,
	verification_level: null,
	exclude_patterns: null,
	target_files: null,
	error_message: null,
} satisfies AgentTask;

test("AgentAudit Header renders metric tags beside the intelligent audit title", () => {
	const markup = renderToStaticMarkup(
		createElement(Header, {
			title: "智能审计详情",
			task: taskFixture,
			isRunning: true,
			isCancelling: false,
			onBack: () => {},
			onCancel: () => {},
			onExport: () => {},
			metricTags: ["高危 3", "已验证 2"],
		}),
	);

	assert.match(markup, /data-agent-audit-title-row="true"/);
	assert.match(
		markup,
		/data-agent-audit-title-row="true"[\s\S]*智能审计详情[\s\S]*智能审计概要标签[\s\S]*高危 3[\s\S]*已验证 2/,
	);
	assert.match(
		markup,
		/h-9 max-w-\[260px\] truncate rounded-full border-border\/70 bg-muted\/30 px-3 text-sm font-semibold/,
	);
	assert.match(markup, /中止/);
	assert.match(markup, /导出报告/);
	assert.match(markup, /返回/);
});
