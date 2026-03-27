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

function createSnapshotFixture() {
	return {
		generated_at: "2026-03-23T03:00:00.000Z",
		total_scan_duration_ms: 90061000,
		scan_runs: [],
		vulns: [],
		rule_confidence: [],
		rule_confidence_by_language: [],
		cwe_distribution: [
			{
				cwe_id: "CWE-79",
				cwe_name: "跨站脚本",
				total_findings: 3,
				opengrep_findings: 1,
				agent_findings: 2,
				bandit_findings: 0,
			},
		],
		summary: {
			total_projects: 12,
			current_effective_findings: 48,
			current_verified_findings: 21,
			total_model_tokens: 1482360,
			false_positive_rate: 0.12,
			scan_success_rate: 0.92,
			avg_scan_duration_ms: 825,
			window_scanned_projects: 10,
			window_new_effective_findings: 18,
			window_verified_findings: 9,
			window_false_positive_rate: 0.08,
			window_scan_success_rate: 0.94,
			window_avg_scan_duration_ms: 810,
		},
		daily_activity: [
			{
				date: "2026-03-20",
				completed_scans: 4,
				agent_findings: 3,
				opengrep_findings: 5,
				gitleaks_findings: 2,
				bandit_findings: 1,
				phpstan_findings: 2,
				yasa_findings: 1,
			},
			{
				date: "2026-03-21",
				completed_scans: 5,
				agent_findings: 4,
				opengrep_findings: 6,
				gitleaks_findings: 3,
				bandit_findings: 2,
				phpstan_findings: 2,
				yasa_findings: 1,
			},
		],
		verification_funnel: {
			raw_findings: 30,
			effective_findings: 18,
			verified_findings: 9,
			false_positive_count: 4,
		},
		task_status_breakdown: {
			pending: 0,
			running: 2,
			completed: 12,
			failed: 1,
			interrupted: 1,
			cancelled: 0,
		},
		engine_breakdown: [
			{
				engine: "llm",
				completed_scans: 3,
				effective_findings: 18,
				verified_findings: 9,
				false_positive_count: 1,
				avg_scan_duration_ms: 1200,
				success_rate: 1,
			},
			{
				engine: "opengrep",
				completed_scans: 4,
				effective_findings: 15,
				verified_findings: 4,
				false_positive_count: 1,
				avg_scan_duration_ms: 1000,
				success_rate: 1,
			},
			{
				engine: "gitleaks",
				completed_scans: 4,
				effective_findings: 9,
				verified_findings: 2,
				false_positive_count: 1,
				avg_scan_duration_ms: 900,
				success_rate: 1,
			},
			{
				engine: "bandit",
				completed_scans: 3,
				effective_findings: 7,
				verified_findings: 2,
				false_positive_count: 0,
				avg_scan_duration_ms: 760,
				success_rate: 1,
			},
			{
				engine: "phpstan",
				completed_scans: 2,
				effective_findings: 5,
				verified_findings: 1,
				false_positive_count: 0,
				avg_scan_duration_ms: 700,
				success_rate: 1,
			},
			{
				engine: "yasa",
				completed_scans: 2,
				effective_findings: 4,
				verified_findings: 1,
				false_positive_count: 0,
				avg_scan_duration_ms: 680,
				success_rate: 0.5,
			},
		],
		project_hotspots: [],
		language_risk: [
			{
				language: "TypeScript",
				project_count: 4,
				loc_number: 182400,
				effective_findings: 28,
				verified_findings: 12,
				false_positive_count: 1,
				findings_per_kloc: 15.35,
				rules_high: 4,
				rules_medium: 2,
			},
			{
				language: "Python",
				project_count: 3,
				loc_number: 124600,
				effective_findings: 16,
				verified_findings: 7,
				false_positive_count: 1,
				findings_per_kloc: 12.84,
				rules_high: 2,
				rules_medium: 3,
			},
		],
		recent_tasks: [
			{
				task_id: "at-1",
				task_type: "混合扫描",
				title: "混合扫描 · Alpha Gateway",
				engine: "llm",
				status: "running",
				created_at: "2026-03-23T02:30:00.000Z",
				detail_path: "/agent-audit/at-1",
			},
			{
				task_id: "at-2",
				task_type: "智能扫描",
				title: "智能扫描 · Beta API",
				engine: "llm",
				status: "completed",
				created_at: "2026-03-23T01:30:00.000Z",
				detail_path: "/agent-audit/at-2",
			},
			{
				task_id: "og-1",
				task_type: "静态扫描",
				title: "静态扫描 · Gamma Portal",
				engine: "opengrep",
				status: "failed",
				created_at: "2026-03-23T00:30:00.000Z",
				detail_path: "/tasks/static",
			},
			{
				task_id: "ps-1",
				task_type: "静态扫描",
				title: "静态扫描 · Delta PHP",
				engine: "phpstan",
				status: "completed",
				created_at: "2026-03-22T23:30:00.000Z",
				detail_path: "/tasks/static",
			},
			{
				task_id: "ya-1",
				task_type: "静态扫描",
				title: "静态扫描 · Echo Console",
				engine: "yasa",
				status: "interrupted",
				created_at: "2026-03-22T22:30:00.000Z",
				detail_path: "/tasks/static",
			},
		],
		project_risk_distribution: [
			{
				project_id: "p1",
				project_name: "Alpha Gateway",
				critical_count: 3,
				high_count: 7,
				medium_count: 5,
				low_count: 2,
				total_findings: 17,
			},
			{
				project_id: "p2",
				project_name: "Beta API",
				critical_count: 1,
				high_count: 4,
				medium_count: 3,
				low_count: 1,
				total_findings: 9,
			},
		],
		verified_vulnerability_types: [
			{ type_code: "CWE-89", type_name: "SQL 注入", verified_count: 8 },
			{ type_code: "CWE-79", type_name: "跨站脚本", verified_count: 5 },
		],
		static_engine_rule_totals: [
			{ engine: "opengrep", total_rules: 368 },
			{ engine: "gitleaks", total_rules: 214 },
			{ engine: "bandit", total_rules: 172 },
			{ engine: "phpstan", total_rules: 129 },
			{ engine: "yasa", total_rules: 84 },
		],
		language_loc_distribution: [
			{ language: "TypeScript", loc_number: 182400, project_count: 4 },
			{ language: "Python", loc_number: 124600, project_count: 3 },
			{ language: "PHP", loc_number: 109300, project_count: 2 },
		],
	};
}

test("DashboardCommandCenter renders the live single-page dashboard layout", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot: createSnapshotFixture(),
			rangeDays: 14,
			onRangeDaysChange: () => { },
		}),
	);

	assert.match(markup, /项目总数/);
	assert.match(markup, /累计发现漏洞总数/);
	assert.match(markup, /AI验证漏洞总数/);
	assert.match(markup, /累计执行扫描/);
	assert.match(markup, /累计消耗词元/);
	assert.match(markup, /漏洞态势趋势/);
	assert.match(markup, /项目风险统计图/);
	assert.match(markup, /语言风险统计图/);
	assert.match(markup, /漏洞类型统计图/);
	assert.match(markup, /扫描引擎统计图/);
	assert.match(markup, /静态扫描引擎规则统计图/);
	assert.match(markup, /语言代码行数统计图/);
	assert.match(markup, /任务状态/);
	assert.match(markup, /横坐标：日期/);
	assert.match(markup, /纵坐标：漏洞数量/);
	assert.match(markup, /新增风险/);
	assert.match(markup, /已验证/);
	assert.match(markup, /data-panel="trend"/);
	assert.match(markup, /aria-pressed="true"/);
	assert.match(markup, /混合扫描 · Alpha Gateway/);
	assert.match(markup, /智能扫描 · Beta API/);
	assert.match(markup, /静态扫描 · Gamma Portal/);
	assert.match(markup, /静态扫描 · Delta PHP/);
	assert.doesNotMatch(markup, /静态扫描 · Echo Console/);
	assert.match(markup, /查看详情/);
	assert.match(markup, /上一页/);
	assert.match(markup, /下一页/);
	assert.doesNotMatch(markup, /共 \d+ 条/);
	assert.doesNotMatch(markup, /第 \d+ \/ \d+ 页/);
	assert.doesNotMatch(markup, /排行榜/);
	assert.doesNotMatch(markup, /等待中/);
});

test("DashboardCommandCenter recent static task uses the provided aggregated detail path", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.recent_tasks = [
		{
			task_id: "gl-batch",
			task_type: "静态扫描",
			title: "静态扫描 · Gamma Portal",
			engine: "gitleaks",
			status: "completed",
			created_at: "2026-03-23T00:30:00.000Z",
			detail_path:
				"/static-analysis/gl-batch?gitleaksTaskId=gl-batch&banditTaskId=ba-batch",
		},
	];

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot,
			rangeDays: 14,
			onRangeDaysChange: () => { },
		}),
	);

	assert.match(
		markup,
		/href="\/static-analysis\/gl-batch\?gitleaksTaskId=gl-batch&amp;banditTaskId=ba-batch"/,
	);
	assert.doesNotMatch(markup, /href="\/tasks\/static"/);
});

test("DashboardCommandCenter shows an empty state when no recent tasks are available", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.recent_tasks = [];

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot,
			rangeDays: 14,
			onRangeDaysChange: () => { },
		}),
	);

	assert.match(markup, /暂无最近任务/);
	assert.doesNotMatch(markup, /共 \d+ 条/);
	assert.doesNotMatch(markup, /上一页/);
	assert.doesNotMatch(markup, /下一页/);
});

test("DashboardCommandCenter uses enlarged axes and fixed chart spacing constants", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.equal(module.HORIZONTAL_STATS_AXIS_FONT_SIZE, 16);
	assert.equal(module.HORIZONTAL_STATS_LABEL_FONT_SIZE, 16);
	assert.equal(module.HORIZONTAL_STATS_Y_AXIS_MIN_WIDTH, 84);
	assert.equal(module.HORIZONTAL_STATS_Y_AXIS_MAX_WIDTH, 120);
	assert.equal(module.HORIZONTAL_STATS_BAR_SIZE, 12);
	assert.equal(module.HORIZONTAL_STATS_ROW_HEIGHT, 46);
	assert.equal(module.HORIZONTAL_STATS_BAR_CATEGORY_GAP, 4);
	assert.deepEqual(module.HORIZONTAL_STATS_CHART_MARGIN, {
		top: 8,
		right: 24,
		left: 12,
		bottom: 8,
	});
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

test("estimateHorizontalStatsYAxisWidth shrinks short labels while keeping long labels readable", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.equal(
		module.estimateHorizontalStatsYAxisWidth([
			{
				label: "llm",
				meta: "",
				total: 1,
				critical: 0,
				high: 0,
				medium: 0,
				low: 0,
				tone: "low",
			},
		]),
		module.HORIZONTAL_STATS_Y_AXIS_MIN_WIDTH,
	);
	assert.equal(
		module.estimateHorizontalStatsYAxisWidth([
			{
				label: "Alpha Gateway",
				meta: "",
				total: 1,
				critical: 0,
				high: 0,
				medium: 0,
				low: 0,
				tone: "high",
			},
		]),
		module.HORIZONTAL_STATS_Y_AXIS_MAX_WIDTH,
	);
});

test("vulnerability-types view uses 5-step x-axis ticks", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.deepEqual(module.getHorizontalStatsXAxisProps("vulnerability-types"), {
		minTickGap: 0,
		tickCount: 6,
		allowDecimals: false,
		domain: [0, "dataMax"],
		ticks: undefined,
	});
	assert.deepEqual(module.getHorizontalStatsXAxisProps("language-risk"), {
		minTickGap: 0,
		tickCount: undefined,
		allowDecimals: false,
		domain: [0, "auto"],
		ticks: undefined,
	});
	assert.deepEqual(module.getHorizontalStatsXAxisProps("vulnerability-types", [
		{
			label: "CWE-89",
			meta: "SQL 注入",
			total: 8,
			critical: 0,
			high: 0,
			medium: 0,
			low: 0,
			tone: "medium",
		},
		{
			label: "CWE-79",
			meta: "跨站脚本",
			total: 13,
			critical: 0,
			high: 0,
			medium: 0,
			low: 0,
			tone: "high",
		},
	]).ticks, [0, 5, 10, 15]);
});

test("formatCumulativeDuration formats scan durations with zh units", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.equal(module.formatCumulativeDuration(0), "0秒");
	assert.equal(module.formatCumulativeDuration(7050), "7秒");
	assert.equal(module.formatCumulativeDuration(61000), "1分 1秒");
	assert.equal(module.formatCumulativeDuration(3605000), "1时 0分 5秒");
	assert.equal(module.formatCumulativeDuration(90061000), "1天 1时 1分 1秒");
});

test("recent task pagination uses four items per page and clamps invalid pages", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const tasks = createSnapshotFixture().recent_tasks;

	assert.equal(module.DASHBOARD_RECENT_TASKS_PAGE_SIZE, 4);

	assert.deepEqual(module.paginateRecentTasks([], 1), {
		items: [],
		currentPage: 1,
		totalPages: 1,
		totalCount: 0,
	});
	assert.deepEqual(
		module.paginateRecentTasks(tasks.slice(0, 1), 99),
		{
			items: tasks.slice(0, 1),
			currentPage: 1,
			totalPages: 1,
			totalCount: 1,
		},
	);
	assert.deepEqual(
		module.paginateRecentTasks(tasks.slice(0, 4), 0),
		{
			items: tasks.slice(0, 4),
			currentPage: 1,
			totalPages: 1,
			totalCount: 4,
		},
	);
	assert.deepEqual(
		module.paginateRecentTasks(tasks.slice(0, 5), 2),
		{
			items: tasks.slice(4, 5),
			currentPage: 2,
			totalPages: 2,
			totalCount: 5,
		},
	);
	assert.deepEqual(
		module.paginateRecentTasks(tasks, 999),
		{
			items: tasks.slice(4, 5),
			currentPage: 2,
			totalPages: 2,
			totalCount: 5,
		},
	);
});
