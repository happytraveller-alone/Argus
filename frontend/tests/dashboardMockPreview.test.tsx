import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

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

test("DashboardMockPreview renders single-page command center with sidebar and task status", async () => {
	const module = await importOrFail<any>(
		"../src/pages/DashboardMockPreview.tsx",
	);

	const markup = renderToStaticMarkup(createElement(module.default));

	assert.match(markup, /漏洞态势趋势/);
	assert.match(markup, /项目风险统计图/);
	assert.match(markup, /语言风险统计图/);
	assert.match(markup, /漏洞类型统计图/);
	assert.match(markup, /扫描引擎统计图/);
	assert.match(markup, /扫描规则统计图/);
	assert.match(markup, /项目语言统计图/);
	assert.match(markup, /任务状态/);
	assert.match(markup, /项目总数/);
	assert.match(markup, /累计发现漏洞总数/);
	assert.match(markup, /AI验证漏洞总数/);
	assert.match(markup, /累计执行扫描/);
	assert.match(markup, /累计消耗词元/);
	assert.match(markup, /Alpha Gateway/);
	assert.match(markup, /TypeScript/);
	assert.match(markup, /SQL 注入/);
	assert.match(markup, /data-panel="trend"/);
	assert.match(markup, /aria-pressed="true"/);
	assert.match(markup, /横坐标：日期/);
	assert.match(markup, /纵坐标：漏洞数量/);
	assert.match(markup, /查看近七日当日新增漏洞发现与来源构成的波动/);
	// assert.match(markup, /最近创建任务/);
	assert.match(markup, /查看详情/);
	assert.match(markup, /智能扫描 · Alpha Gateway/);
	assert.match(markup, /执行进度 92%/);
	assert.doesNotMatch(markup, /静态扫描 · Helios CRM/);
	assert.doesNotMatch(markup, /模拟数据预览/);
	assert.doesNotMatch(markup, /排行榜/);
	assert.doesNotMatch(markup, /等待中/);
	assert.doesNotMatch(markup, /PROJECT_RISK_ROWS/);
	assert.doesNotMatch(markup, /LANGUAGE_RISK_ROWS/);
	assert.doesNotMatch(markup, /VULNERABILITY_TYPE_ROWS/);
});

test("dashboard mock preview model exposes seven switchable views with sorted chart data", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/dashboardMockPreviewModel.ts",
	);

	const views = module.DASHBOARD_PREVIEW_VIEWS;
	assert.deepEqual(
		views.map((view: { id: string }) => view.id),
		[
			"trend",
			"project-risk",
			"language-risk",
			"vulnerability-types",
			"scan-engines",
			"static-engine-rules",
			"language-lines",
		],
	);

	const projectRows = module.getPreviewLeaderboardRows("project-risk");
	assert.equal(projectRows[0].label, "Alpha Gateway");
	assert.equal(projectRows[0].segments[0].tone, "critical");
	assert.equal(projectRows[0].segments[0].value >= projectRows[1].segments[0].value, true);
	assert.equal(projectRows[0].total >= projectRows[1].total, true);
	assert.equal(projectRows.length, 10);
	assert.equal(projectRows[9].total <= projectRows[8].total, true);

	const languageRows = module.getPreviewLeaderboardRows("language-risk");
	assert.equal(languageRows[0].label, "TypeScript");
	assert.equal(languageRows[0].total >= languageRows[1].total, true);
	assert.equal(languageRows.every((row: { segments: unknown[] }) => row.segments.length === 1), true);
	assert.equal(languageRows.length, 10);
	assert.equal(languageRows[9].total <= languageRows[8].total, true);

	const vulnerabilityRows = module.getPreviewLeaderboardRows("vulnerability-types");
	assert.equal(vulnerabilityRows[0].label, "CWE-89");
	assert.equal(vulnerabilityRows[0].total >= vulnerabilityRows[1].total, true);
	assert.match(vulnerabilityRows[0].meta, /SQL 注入/);
	assert.equal(vulnerabilityRows.length, 10);
	assert.equal(vulnerabilityRows[9].total <= vulnerabilityRows[8].total, true);

	const engineRows = module.getPreviewLeaderboardRows("scan-engines");
	assert.equal(engineRows[0].label, "llm");
	assert.equal(engineRows[0].total >= engineRows[1].total, true);
	assert.match(engineRows[0].meta, /智能扫描/);
	assert.equal(engineRows.every((row: { segments: unknown[] }) => row.segments.length === 1), true);
	assert.equal(engineRows.length, 5);
	assert.equal(engineRows[4].total <= engineRows[3].total, true);

	const staticRuleRows = module.getPreviewLeaderboardRows("static-engine-rules");
	assert.equal(staticRuleRows[0].label, "opengrep");
	assert.equal(staticRuleRows[0].total >= staticRuleRows[1].total, true);
	assert.match(staticRuleRows[0].meta, /规则/);
	assert.equal(staticRuleRows.every((row: { segments: unknown[] }) => row.segments.length === 1), true);
	assert.equal(staticRuleRows.length, 4);
	assert.equal(staticRuleRows[3].label, "phpstan");
	assert.equal(staticRuleRows[3].total <= staticRuleRows[2].total, true);

	const languageLineRows = module.getPreviewLeaderboardRows("language-lines");
	assert.equal(languageLineRows[0].label, "TypeScript");
	assert.equal(languageLineRows[0].total >= languageLineRows[1].total, true);
	assert.match(languageLineRows[0].meta, /代码行/);
	assert.equal(languageLineRows.every((row: { segments: unknown[] }) => row.segments.length === 1), true);
	assert.equal(languageLineRows.length, 10);
	assert.equal(languageLineRows[9].total <= languageLineRows[8].total, true);

	assert.equal(
		module.DASHBOARD_PREVIEW_TASK_STATUS.some(
			(item: { label: string }) => item.label === "等待中",
		),
		false,
	);

	const recentTasks = module.getRecentPreviewTasks();
	assert.equal(recentTasks.length, 5);
	assert.equal(recentTasks[0].title, "智能扫描 · Alpha Gateway");
	assert.equal(recentTasks[0].progress, 92);
	assert.equal(recentTasks[0].createdAt >= recentTasks[1].createdAt, true);
	assert.equal(recentTasks[4].title, "静态扫描 · Vega Billing");
	assert.deepEqual(module.DASHBOARD_PREVIEW_TREND[0], {
		date: "03-17",
		totalNewFindings: 18,
		staticFindings: 9,
		intelligentVerifiedFindings: 9,
	});
});

test("dashboard mock preview chart sizing uses enlarged axes and narrower bars", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardMockPreviewCanvas.tsx",
	);

	assert.equal(module.HORIZONTAL_STATS_AXIS_FONT_SIZE, 16);
	assert.equal(module.HORIZONTAL_STATS_LABEL_FONT_SIZE, 16);
	assert.equal(module.HORIZONTAL_STATS_Y_AXIS_WIDTH, 128);
	assert.equal(module.HORIZONTAL_STATS_BAR_SIZE, 14);
	assert.equal(module.HORIZONTAL_STATS_ROW_HEIGHT, 46);
	assert.equal(module.HORIZONTAL_STATS_BAR_CATEGORY_GAP, 4);
	assert.equal(
		module.HORIZONTAL_STATS_META_ROW_CLASSNAME,
		"mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
	);
	assert.equal(
		module.HORIZONTAL_STATS_META_LEGEND_CLASSNAME,
		"flex flex-wrap justify-start gap-2 sm:justify-end",
	);
	assert.equal(module.TOP_STATS_GRID_CLASSNAME, "grid grid-cols-2 gap-3 xl:grid-cols-5");
});
