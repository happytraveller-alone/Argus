import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

async function importOrFail<TModule = Record<string, unknown>>(
	relativePath: string,
): Promise<TModule> {
	try {
		return (await import(relativePath)) as TModule;
	} catch (error) {
		assert.fail(
			`expected helper module ${relativePath} to exist: ${error instanceof Error ? error.message : String(error)}`,
		);
	}
}

test("ProjectsTable renders hover metric popovers without nested trigger frames", async () => {
	const tableModule = await importOrFail<any>(
		"../src/pages/projects/components/ProjectsTable.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(SsrRouter, {}, createElement(tableModule.default, {
			rows: [
				{
					id: "p1",
					name: "Demo Project",
					detailPath: "/projects/p1",
					detailState: { from: "/projects" },
					sizeText: "10 文件 / 200 行",
					vulnerabilityStats: {
						critical: 3,
						high: 5,
						medium: 8,
						low: 13,
						total: 29,
					},
					aiVerifiedStats: {
						critical: 1,
						high: 4,
						medium: 4,
						low: 2,
						total: 11,
					},
					executionStats: { completed: 2, running: 1 },
					metricsStatus: "ready",
					metricsStatusMessage: null,
					actions: {
						canCreateScan: true,
						canBrowseCode: true,
						browseCodePath: "/projects/p1/code-browser",
						browseCodeState: { from: "/projects#project-browser" },
						browseCodeDisabledReason: null,
					},
				},
				{
					id: "p2",
					name: "Disabled Project",
					detailPath: "/projects/p2",
					detailState: { from: "/projects" },
					sizeText: "-",
					vulnerabilityStats: {
						critical: 0,
						high: 1,
						medium: 2,
						low: 3,
						total: 6,
					},
					aiVerifiedStats: {
						critical: 0,
						high: 0,
						medium: 0,
						low: 0,
						total: 0,
					},
					executionStats: { completed: 0, running: 0 },
					metricsStatus: "pending",
					metricsStatusMessage: "指标同步中...",
					actions: {
						canCreateScan: true,
						canBrowseCode: false,
						browseCodePath: "/projects/p2/code-browser",
						browseCodeState: { from: "/projects#project-browser" },
						browseCodeDisabledReason: "仅 ZIP 类型项目支持代码浏览",
					},
				},
			],
			onCreateScan: () => {},
		})),
	);

	assert.match(markup, /Demo Project/);
	assert.match(markup, /Disabled Project/);
	assert.match(markup, /项目/);
	assert.match(markup, /大小/);
	assert.match(markup, /操作/);
	// assert.match(markup, /执行任务/);
	assert.match(markup, /发现潜在漏洞/);
	assert.match(markup, /AI验证漏洞/);
	assert.match(markup, /查看详情/);
	assert.match(markup, /代码浏览/);
	assert.match(markup, /创建扫描/);
	assert.match(markup, />29</);
	assert.match(markup, />11</);
	assert.match(markup, />6</);
	assert.match(markup, />0</);
	assert.match(markup, /仅 ZIP 类型项目支持代码浏览/);
	assert.match(markup, /指标同步中\.\.\./);
	assert.doesNotMatch(markup, /序号/);
	assert.doesNotMatch(markup, /全选当前页/);
	assert.doesNotMatch(markup, /选择项目/);
	assert.match(markup, /<thead[\s\S]*?<\/thead>/);
	assert.match(markup, /<th[\s\S]*?项目名称[\s\S]*?<\/th>/);
	assert.match(markup, /<th[\s\S]*?项目大小[\s\S]*?<\/th>/);
	// assert.match(markup, /<th[\s\S]*?执行任务[\s\S]*?<\/th>/);
	assert.match(markup, /<th[\s\S]*?发现潜在漏洞[\s\S]*?<\/th>/);
	assert.match(markup, /<th[\s\S]*?AI验证漏洞[\s\S]*?<\/th>/);
	assert.match(markup, /<th[^>]*>操作<\/th>/);
	assert.doesNotMatch(markup, /项目概览|体量概览|快捷操作|任务概览|风险概览/);
	assert.doesNotMatch(markup, /名称与入口|规模与体量|详情 \/ 浏览 \/ 扫描|完成 \/ 运行中|按风险等级分布/);
	assert.doesNotMatch(markup, /data-project-group-header=/);
	assert.doesNotMatch(markup, /data-project-group-label=/);
	assert.match(markup, /data-project-metric-group="vulnerabilities"/);
	assert.match(markup, /data-project-metric-group="ai-verified"/);
	assert.match(markup, /data-project-metric-trigger="vulnerabilities"/);
	assert.match(markup, /data-project-metric-trigger="ai-verified"/);
	assert.match(markup, /data-project-metric-popover="vulnerabilities"/);
	assert.match(markup, /data-project-metric-popover="ai-verified"/);
	assert.match(markup, /data-project-metric-item="critical"/);
	assert.match(markup, /data-project-metric-item="high"/);
	assert.match(markup, /data-project-metric-item="medium"/);
	assert.match(markup, /data-project-metric-item="low"/);
	assert.match(markup, /inline-flex min-w-\[3\.25rem\] items-center justify-center rounded-full border px-3 py-1/);
	assert.match(markup, /flex items-center justify-center relative/);
	assert.match(markup, /font-semibold tabular-nums text-\[18px\]/);
	assert.doesNotMatch(markup, /inline-flex min-w-\[5\.5rem\] items-center justify-center rounded-md border px-3 py-1\.5/);
	assert.match(markup, /aria-haspopup="dialog"/);
	assert.doesNotMatch(markup, /data-project-metric-grid=/);
	assert.doesNotMatch(markup, /group relative inline-flex min-w-\[4\.5rem\] items-center justify-center rounded-full border border-border\/60 bg-background\/40 p-1/);
	assert.doesNotMatch(markup, /暂未发现漏洞/);
	assert.doesNotMatch(markup, /min-w-\[1360px\]/);
	assert.match(markup, /style="width:100%;min-width:\d+px"/);
	assert.doesNotMatch(markup, /whitespace-nowrap text-\[16px\]/);
	assert.match(markup, /border-b-2/);
	assert.match(markup, /border-r-2 border-border\/90/);
	assert.match(markup, /border-l-2 border-border\/95/);
	assert.match(markup, /text-\[14px\] font-semibold uppercase/);
	assert.match(markup, /mx-auto block max-w-\[180px\] truncate text-center text-\[16px\] font-semibold/);
	assert.match(markup, /text-center text-\[16px\] text-muted-foreground/);
	assert.match(markup, /justify-center gap-2 text-\[16px\]/);
	assert.ok(markup.indexOf("查看详情") < markup.indexOf("代码浏览"));
	assert.ok(markup.indexOf("代码浏览") < markup.indexOf("创建扫描"));
	assert.ok(!markup.includes(">状态<"));
	assert.match(markup, /disabled/);
});

test("ProjectsTable hides zero-count vulnerability severities and shows empty placeholder", async () => {
	const tableModule = await importOrFail<any>(
		"../src/pages/projects/components/ProjectsTable.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(SsrRouter, {}, createElement(tableModule.default, {
			rows: [
				{
					id: "p1",
					name: "Mixed Risk Project",
					detailPath: "/projects/p1",
					detailState: { from: "/projects" },
					sizeText: "1.00 Mb",
					vulnerabilityStats: {
						critical: 0,
						high: 2,
						medium: 0,
						low: 1,
						total: 3,
					},
					aiVerifiedStats: {
						critical: 0,
						high: 1,
						medium: 0,
						low: 0,
						total: 1,
					},
					executionStats: { completed: 0, running: 0 },
					metricsStatus: "ready",
					metricsStatusMessage: null,
					actions: {
						canCreateScan: true,
						canBrowseCode: true,
						browseCodePath: "/projects/p1/code-browser",
						browseCodeState: { from: "/projects" },
						browseCodeDisabledReason: null,
					},
				},
				{
					id: "p2",
					name: "Empty Risk Project",
					detailPath: "/projects/p2",
					detailState: { from: "/projects" },
					sizeText: "2.00 Mb",
					vulnerabilityStats: {
						critical: 0,
						high: 0,
						medium: 0,
						low: 0,
						total: 0,
					},
					aiVerifiedStats: {
						critical: 0,
						high: 0,
						medium: 0,
						low: 0,
						total: 0,
					},
					executionStats: { completed: 0, running: 0 },
					metricsStatus: "ready",
					metricsStatusMessage: null,
					actions: {
						canCreateScan: true,
						canBrowseCode: true,
						browseCodePath: "/projects/p2/code-browser",
						browseCodeState: { from: "/projects" },
						browseCodeDisabledReason: null,
					},
				},
			],
			onCreateScan: () => {},
		})),
	);

	assert.match(markup, /Mixed Risk Project[\s\S]*?data-project-metric-trigger="vulnerabilities"[\s\S]*?>3</);
	assert.match(markup, /Mixed Risk Project[\s\S]*?data-project-metric-trigger="ai-verified"[\s\S]*?>1</);
	assert.match(markup, /Empty Risk Project[\s\S]*?data-project-metric-trigger="vulnerabilities"[\s\S]*?>0</);
	assert.match(markup, /Empty Risk Project[\s\S]*?data-project-metric-trigger="ai-verified"[\s\S]*?>0</);
	assert.doesNotMatch(markup, /暂未发现漏洞/);
});

test("ProjectsTable keeps metric popovers but removes the old outer trigger frame", async () => {
	const tableModule = await importOrFail<any>(
		"../src/pages/projects/components/ProjectsTable.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(SsrRouter, {}, createElement(tableModule.default, {
			rows: [
				{
					id: "p1",
					name: "Portal Metrics Project",
					detailPath: "/projects/p1",
					detailState: { from: "/projects" },
					sizeText: "1.00 Mb",
					vulnerabilityStats: {
						critical: 1,
						high: 2,
						medium: 3,
						low: 4,
						total: 10,
					},
					aiVerifiedStats: {
						critical: 1,
						high: 1,
						medium: 1,
						low: 1,
						total: 4,
					},
					executionStats: { completed: 1, running: 0 },
					metricsStatus: "ready",
					metricsStatusMessage: null,
					actions: {
						canCreateScan: true,
						canBrowseCode: true,
						browseCodePath: "/projects/p1/code-browser",
						browseCodeState: { from: "/projects" },
						browseCodeDisabledReason: null,
					},
				},
			],
			onCreateScan: () => {},
		})),
	);

	assert.match(markup, /class="[^"]*overflow-visible[^"]*"/);
	assert.match(markup, /data-project-metric-trigger="vulnerabilities"/);
	assert.match(markup, /data-project-metric-popover="vulnerabilities"/);
	assert.doesNotMatch(markup, /group relative inline-flex min-w-\[4\.5rem\] items-center justify-center rounded-full border border-border\/60 bg-background\/40 p-1/);
	assert.doesNotMatch(markup, /data-slot="table-container" class="[^"]*overflow-x-auto[^"]*rounded-sm border border-border/);
});
