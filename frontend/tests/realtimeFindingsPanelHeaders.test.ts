import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { fileURLToPath } from "node:url";

import RealtimeFindingsPanel, {
	type RealtimeMergedFindingItem,
} from "../src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx";
import type { FindingsViewFilters } from "../src/pages/AgentAudit/types.ts";

globalThis.React = React;

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const realtimeFindingsPanelPath = path.join(
	frontendDir,
	"src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx",
);

const filters: FindingsViewFilters = {
	keyword: "",
	severity: "all",
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
		cwe_id: "CWE-89",
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

	assert.match(markup, /<th[^>]*>漏洞类型<\/th>/);
	assert.match(markup, /<th[^>]*data-no-i18n="true"[^>]*>漏洞危害<\/th>/);
	assert.doesNotMatch(markup, /<th[^>]*>类型 \/ 标题<\/th>/);
	assert.doesNotMatch(markup, /<th[^>]*data-no-i18n="true"[^>]*>命中位置<\/th>/);
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

	assert.match(endedMarkup, />无效<\/span>/);
	assert.match(endedMarkup, />低<\/span>/);
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

test("RealtimeFindingsPanel 保持简洁卡片外观，并为小屏提供表格横向滚动容器", () => {
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

	assert.match(markup, /rounded-xl bg-card\/50/);
	assert.doesNotMatch(markup, /rounded-xl border border-border\/70 bg-card\/50/);
	assert.match(markup, /data-slot="table-container"/);
	assert.match(markup, /overflow-x-auto overflow-y-hidden/);
	assert.match(markup, /min-width:980px/);
});

test("RealtimeFindingsPanel 仅在列表中显示漏洞类型，不再渲染原标题副标题", () => {
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

	assert.match(markup, />CWE-89 SQL注入</);
	assert.doesNotMatch(markup, />SQL 注入</);
});

test("RealtimeFindingsPanel 在无结果时显示漏洞空态文案", () => {
	const markup = renderToStaticMarkup(
		createElement(RealtimeFindingsPanel, {
			taskId: "task-verified-empty",
			items: [],
			isRunning: false,
			currentPhase: null,
			filters,
			onFiltersChange: () => {},
			onOpenDetail: () => {},
		}),
	);

	assert.match(markup, /暂无漏洞/);
	assert.doesNotMatch(markup, />查看全部漏洞<\/button>/);
});

test("RealtimeFindingsPanel 在筛选后无结果时保留过滤态空文案", () => {
	const markup = renderToStaticMarkup(
		createElement(RealtimeFindingsPanel, {
			taskId: "task-filtered-empty",
			items: [
				{
					id: "finding-verified",
					fingerprint: "fingerprint-verified",
					title: "SQL 注入",
					severity: "high",
					display_severity: "high",
					verification_progress: "verified",
					vulnerability_type: "SQL Injection",
					cwe_id: "CWE-89",
					file_path: "src/api/user.ts",
					line_start: 18,
					line_end: 18,
					confidence: 0.92,
					is_verified: true,
				},
			],
			isRunning: false,
			currentPhase: null,
			filters: {
				keyword: "XSS",
				severity: "all",
			},
			onFiltersChange: () => {},
			onOpenDetail: () => {},
		}),
	);

	assert.match(markup, /暂无符合条件的漏洞/);
	assert.doesNotMatch(markup, /暂无漏洞/);
});

test("RealtimeFindingsPanel 在全部为入库空置信度时隐藏置信度列且不渲染占位横杠", () => {
	const noConfidenceItems: RealtimeMergedFindingItem[] = [
		{
			id: "finding-2",
			fingerprint: "fingerprint-2",
			title: "认证绕过",
			severity: "high",
			display_severity: "high",
			verification_progress: "verified",
			vulnerability_type: "Auth Bypass",
			file_path: "src/auth/login.ts",
			line_start: 42,
			line_end: 42,
			confidence: null,
			is_verified: true,
		},
	];

	const markup = renderToStaticMarkup(
		createElement(RealtimeFindingsPanel, {
			taskId: "task-1",
			items: noConfidenceItems,
			isRunning: false,
			currentPhase: null,
			filters,
			onFiltersChange: () => {},
			onOpenDetail: () => {},
		}),
	);

	assert.doesNotMatch(markup, />置信度<\/th>/);
	assert.doesNotMatch(markup, />-<\/span>/);
	assert.doesNotMatch(markup, /同危害按置信度降序/);
});

test("RealtimeFindingsPanel 新增漏洞状态列与判真判假按钮，并可按 updatingKey 精准禁用当前行", () => {
	const markup = renderToStaticMarkup(
		createElement(RealtimeFindingsPanel, {
			taskId: "task-1",
			items: [
				{
					id: "finding-open",
					fingerprint: "fingerprint-open",
					title: "SQL 注入",
					severity: "high",
					display_severity: "high",
					verification_progress: "pending",
					vulnerability_type: "SQL Injection",
					cwe_id: "CWE-89",
					file_path: "src/api/user.ts",
					line_start: 18,
					line_end: 18,
					confidence: 0.92,
					is_verified: false,
				},
				{
					id: "finding-verified",
					fingerprint: "fingerprint-verified",
					title: "命令注入",
					severity: "critical",
					display_severity: "critical",
					verification_progress: "verified",
					vulnerability_type: "Command Injection",
					cwe_id: "CWE-78",
					file_path: "src/exec.ts",
					line_start: 7,
					line_end: 7,
					confidence: 0.88,
					is_verified: true,
					status: "verified",
				},
			],
			isRunning: false,
			currentPhase: null,
			filters,
			onFiltersChange: () => {},
			onOpenDetail: () => {},
			updatingKey: "finding-open:verified",
			getDisplayStatus: (item: RealtimeMergedFindingItem) =>
				item.id === "finding-verified" ? "verified" : "open",
			onToggleStatus: () => {},
		}),
	);

	assert.match(markup, /<th[^>]*>漏洞状态<\/th>/);
	assert.match(markup, />待验证<\/span>/);
	assert.match(markup, />确报<\/span>/);
	assert.match(markup, />判真<\/button>/);
	assert.match(markup, />判假<\/button>/);
	assert.equal(
		(
			markup.match(
				/<button(?=[^>]*aria-pressed="(?:true|false)")(?=[^>]*disabled="")[^>]*>/g,
			) ?? []
		).length,
		2,
	);
});

test("RealtimeFindingsPanel 搜索框直接跟随外层容器起始线，不再额外左缩进", () => {
	const source = readFileSync(realtimeFindingsPanelPath, "utf8");

	assert.match(
		source,
		/className="flex flex-wrap items-center gap-3 border-b border-border\/70 px-4 py-3"/,
	);
	assert.match(
		source,
		/className="relative min-w-0 flex-1 basis-\[320px\]"/,
	);
	assert.doesNotMatch(
		source,
		/className="relative min-w-0 flex-1 basis-\[320px\] pl-4"/,
	);
});

test("RealtimeFindingsPanel 渲染搜索框与漏洞状态列，并保持 verified-only 空态语义", () => {
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

	assert.match(markup, /placeholder="搜索漏洞类型 \/ 危害"/);
	assert.match(markup, /漏洞状态/);
	assert.match(markup, /待验证/);
	assert.doesNotMatch(markup, /处理状态/);
	assert.doesNotMatch(markup, /查看全部漏洞/);
});

test("RealtimeFindingsPanel 翻页按钮只更新页码，不触发过滤模式切换", () => {
	const source = readFileSync(realtimeFindingsPanelPath, "utf8");

	assert.match(
		source,
		/onClick=\{\(\) =>\s*updatePagination\(\{ page: Math\.max\(tableState\.page - 1, 1\) \}\)\s*\}/,
	);
	assert.match(
		source,
		/onClick=\{\(\) =>\s*updatePagination\(\{\s*page: Math\.min\(tableState\.page \+ 1, tableState\.totalPages\),\s*\}\)\s*\}/,
	);
	assert.doesNotMatch(
		source,
		/onClick=\{\(\) => props\.onFiltersChange\(/,
	);
	assert.match(
		source,
		/props\.onPaginationChange\?\.\(resolved\.routeSync,\s*source\)/,
	);
	assert.match(
		source,
		/共 \{tableState\.totalRows\.toLocaleString\(\)\} 条，当前显示/,
	);
});
