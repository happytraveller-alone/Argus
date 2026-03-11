import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import RealtimeFindingsPanel, {
	type RealtimeMergedFindingItem,
} from "../src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx";
import type { FindingsViewFilters } from "../src/pages/AgentAudit/types.ts";

globalThis.React = React;

const filters: FindingsViewFilters = {
	keyword: "",
	severity: "all",
	verification: "all",
};

const items: RealtimeMergedFindingItem[] = [
	{
		id: "finding-1",
		fingerprint: "fingerprint-1",
		title: "SQL 注入",
		severity: "high",
		display_severity: "high",
		verification_progress: "pending",
		vulnerability_type: "SQL Injection",
		file_path: "src/api/user.ts",
		line_start: 18,
		line_end: 18,
		confidence: 0.92,
		is_verified: false,
	},
];

test("RealtimeFindingsPanel 的命中位置和漏洞危害表头保持精简且禁用自动翻译", () => {
	const markup = renderToStaticMarkup(
		createElement(RealtimeFindingsPanel, {
			taskId: "task-1",
			items,
			isRunning: false,
			currentPhase: null,
			filters,
			onFiltersChange: () => {},
			onOpenDetail: () => {},
		}),
	);

	assert.match(markup, /<th[^>]*data-no-i18n="true"[^>]*>命中位置<\/th>/);
	assert.match(markup, /<th[^>]*data-no-i18n="true"[^>]*>漏洞危害<\/th>/);
	assert.doesNotMatch(markup, />命中位置[^<]+</);
	assert.doesNotMatch(markup, />漏洞危害[^<]+</);
});

test("RealtimeFindingsPanel 对误报项显示查看判定依据并保持运行中禁用", () => {
	const falsePositiveItems: RealtimeMergedFindingItem[] = [
		{
			id: "finding-fp",
			fingerprint: "fingerprint-fp",
			title: "硬编码密钥（示例文件）",
			severity: "low",
			display_severity: "invalid",
			verification_progress: "verified",
			vulnerability_type: "Hardcoded Secret",
			file_path: "fixtures/demo.ts",
			line_start: 7,
			line_end: 7,
			confidence: 0.21,
			is_verified: true,
			authenticity: "false_positive",
			verification_evidence: "示例配置模板，不参与实际部署",
		},
	];

	const endedMarkup = renderToStaticMarkup(
		createElement(RealtimeFindingsPanel, {
			taskId: "task-1",
			items: falsePositiveItems,
			isRunning: false,
			currentPhase: null,
			filters,
			onFiltersChange: () => {},
			onOpenDetail: () => {},
		}),
	);

	assert.match(endedMarkup, />误报<\/span>/);
	assert.match(endedMarkup, />无效<\/span>/);
	assert.doesNotMatch(endedMarkup, />低<\/span>/);
	assert.match(endedMarkup, />查看判定依据<\/button>/);
	assert.doesNotMatch(endedMarkup, />详情<\/button>/);

	const runningMarkup = renderToStaticMarkup(
		createElement(RealtimeFindingsPanel, {
			taskId: "task-1",
			items: falsePositiveItems,
			isRunning: true,
			currentPhase: "verification",
			filters,
			onFiltersChange: () => {},
			onOpenDetail: () => {},
		}),
	);

	assert.match(runningMarkup, />详情<\/button>/);
	assert.match(runningMarkup, /disabled=""/);
});

test("RealtimeFindingsPanel 仅保留最外层模块边框，不再渲染表格容器额外方框", () => {
	const markup = renderToStaticMarkup(
		createElement(RealtimeFindingsPanel, {
			taskId: "task-1",
			items,
			isRunning: false,
			currentPhase: null,
			filters,
			onFiltersChange: () => {},
			onOpenDetail: () => {},
		}),
	);

	assert.match(markup, /rounded-xl border border-border\/70 bg-card\/50/);
	assert.doesNotMatch(markup, /data-slot="table-container"/);
});
