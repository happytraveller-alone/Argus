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
			current_verified_vulnerability_total: 16,
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
				static_findings: 11,
				intelligent_verified_findings: 5,
				total_new_findings: 16,
			},
			{
				date: "2026-03-21",
				completed_scans: 5,
				agent_findings: 4,
				opengrep_findings: 6,
				gitleaks_findings: 3,
				bandit_findings: 2,
				phpstan_findings: 2,
				static_findings: 14,
				intelligent_verified_findings: 5,
				total_new_findings: 19,
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
		task_status_by_scan_type: {
			pending: {
				static: 0,
				intelligent: 0,
			},
			running: {
				static: 1,
				intelligent: 1,
			},
			completed: {
				static: 10,
				intelligent: 2,
			},
			failed: {
				static: 1,
				intelligent: 0,
			},
			interrupted: {
				static: 1,
				intelligent: 0,
			},
			cancelled: {
				static: 0,
				intelligent: 0,
			},
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
				task_type: "智能审计",
				title: "智能审计 · Alpha Gateway",
				engine: "llm",
				status: "running",
				created_at: "2026-03-23T02:30:00.000Z",
				detail_path: "/agent-audit/at-1",
			},
			{
				task_id: "at-2",
				task_type: "智能审计",
				title: "智能审计 · Beta API",
				engine: "llm",
				status: "completed",
				created_at: "2026-03-23T01:30:00.000Z",
				detail_path: "/agent-audit/at-2",
			},
			{
				task_id: "og-1",
				task_type: "静态审计",
				title: "静态审计 · Gamma Portal",
				engine: "opengrep",
				status: "failed",
				created_at: "2026-03-23T00:30:00.000Z",
				detail_path: "/tasks/static",
			},
			{
				task_id: "ps-1",
				task_type: "静态审计",
				title: "静态审计 · Delta PHP",
				engine: "phpstan",
				status: "completed",
				created_at: "2026-03-22T23:30:00.000Z",
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
	assert.match(markup, />16</);
	assert.match(markup, /AI验证漏洞总数/);
	assert.match(markup, /累计执行扫描/);
	assert.match(markup, /累计消耗词元/);
	assert.match(markup, /漏洞态势统计图/);
	assert.match(markup, /项目风险统计图/);
	assert.match(markup, /语言风险统计图/);
	assert.match(markup, /漏洞类型统计图/);
	assert.doesNotMatch(markup, /扫描引擎统计图/);
	assert.doesNotMatch(markup, /扫描规则统计图/);
	assert.match(markup, /项目语言统计图/);
	assert.match(markup, /任务状态/);
	assert.match(markup, /横坐标：日期/);
	assert.match(markup, /纵坐标：漏洞数量/);
	assert.match(markup, /查看近一段时间当日新增漏洞发现与来源构成的波动/);
	assert.match(markup, /truncate whitespace-nowrap text-\[11px\]/);
	assert.match(markup, /data-panel="trend"/);
	assert.match(markup, /aria-pressed="true"/);
	assert.match(markup, /Alpha Gateway/);
	assert.match(markup, /Beta API/);
	assert.match(markup, /Gamma Portal/);
	assert.match(markup, /Delta PHP/);
	assert.match(markup, /查看智能审计任务状态细分/);
	assert.match(markup, /查看静态审计任务状态细分/);
	assert.doesNotMatch(markup, /静态审计 · Echo Console/);
	assert.match(markup, /aria-label="查看 Alpha Gateway 详情"/);
	assert.doesNotMatch(markup, /共 \d+ 条/);
	assert.doesNotMatch(markup, /第 \d+ \/ \d+ 页/);
	assert.doesNotMatch(markup, /排行榜/);
	assert.doesNotMatch(markup, /等待中/);
});

test("DashboardCommandCenter cumulative vulnerability card uses the verified-only backend total", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.summary.current_effective_findings = 999;
	snapshot.summary.current_verified_vulnerability_total = 17;

	assert.equal(module.getDashboardVerifiedCumulativeFindingTotal(snapshot), 17);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot,
			rangeDays: 14,
			onRangeDaysChange: () => {},
		}),
	);
	assert.match(markup, /累计发现漏洞总数[\s\S]*>17</);
	assert.doesNotMatch(markup, /累计发现漏洞总数[\s\S]*>999</);
});

test("DashboardCommandCenter builds trend rows with new daily metrics and share buckets", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	const rows = module.buildTrendRows(snapshot.daily_activity);

	assert.deepEqual(rows, [
		{
			date: "03-20",
			totalNewFindings: 16,
			staticFindings: 11,
			intelligentVerifiedFindings: 5,
			staticShare: 0.6875,
			intelligentShare: 0.3125,
			staticLabel: 11,
			intelligentLabel: 5,
		},
		{
			date: "03-21",
			totalNewFindings: 19,
			staticFindings: 14,
			intelligentVerifiedFindings: 5,
			staticShare: 14 / 19,
			intelligentShare: 5 / 19,
			staticLabel: 14,
			intelligentLabel: 5,
		},
	]);
});

test("task status tooltip items preserve subtype counts, including zero values", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.deepEqual(
		module.buildTaskStatusTooltipItems({
			static: 10,
			intelligent: 2,
		}),
		[
			{ label: "静态审计", value: 10 },
			{ label: "智能审计", value: 2 },
		],
	);
	assert.deepEqual(
		module.buildTaskStatusTooltipItems({
			static: 0,
			intelligent: 0,
		}),
		[
			{ label: "静态审计", value: 0 },
			{ label: "智能审计", value: 0 },
		],
	);
});

test("DashboardCommandCenter builds two audit-type task status sections", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.task_status_breakdown = {
		pending: 3,
		running: 2,
		completed: 12,
		failed: 1,
		interrupted: 1,
		cancelled: 2,
	};
	snapshot.task_status_by_scan_type.pending = {
		static: 1,
		intelligent: 2,
	};
	snapshot.task_status_by_scan_type.running = {
		static: 1,
		intelligent: 1,
	};
	snapshot.task_status_by_scan_type.interrupted = {
		static: 1,
		intelligent: 0,
	};
	snapshot.task_status_by_scan_type.cancelled = {
		static: 0,
		intelligent: 2,
	};

	assert.deepEqual(
		module
			.buildAuditTypeTaskStatusSections(snapshot)
			.map(
				({
					key,
					label,
					total,
					completed,
					running,
					anomaly,
					tasksRoute,
				}: any) => ({
					key,
					label,
					total,
					completed,
					running,
					anomaly,
					tasksRoute,
				}),
			),
		[
		{
			key: "intelligent",
			label: "智能审计",
			total: 7,
			completed: 2,
			running: 3,
			anomaly: 2,
			tasksRoute: "/tasks/intelligent",
		},
		{
			key: "static",
			label: "静态审计",
			total: 14,
			completed: 10,
			running: 2,
			anomaly: 2,
			tasksRoute: "/tasks/static",
		},
		],
	);
});

test("DashboardCommandCenter renders two audit-type task status sections", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.task_status_by_scan_type = {
		pending: { static: 0, intelligent: 0 },
		running: { static: 0, intelligent: 0 },
		completed: { static: 0, intelligent: 0 },
		failed: { static: 0, intelligent: 0 },
		interrupted: { static: 0, intelligent: 0 },
		cancelled: { static: 0, intelligent: 0 },
	};

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot,
			rangeDays: 14,
			onRangeDaysChange: () => {},
		}),
	);

	assert.match(markup, /智能审计/);
	assert.match(markup, /静态审计/);
	assert.match(markup, /查看智能审计任务状态细分/);
	assert.match(markup, /查看静态审计任务状态细分/);
	assert.doesNotMatch(markup, /已完成任务/);
});

test("DashboardCommandCenter recent static task uses the provided aggregated detail path", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.recent_tasks = [
		{
			task_id: "gl-batch",
			task_type: "静态审计",
			title: "静态审计 · Gamma Portal",
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
	assert.match(markup, /aria-label="查看 Gamma Portal 详情"/);
	assert.match(markup, /完成/);
	assert.match(markup, /静态审计/);
	assert.doesNotMatch(markup, /href="\/tasks\/static"/);
});

test("DashboardCommandCenter recent task cards show the latest three tasks in one row", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.recent_tasks = [
		...snapshot.recent_tasks,
		{
			task_id: "cancelled-1",
			task_type: "智能审计",
			title: "智能审计 · Echo Console",
			engine: "llm",
			status: "cancelled",
			created_at: "2026-03-22T22:30:00.000Z",
			detail_path: "/agent-audit/cancelled-1",
		},
	];

	assert.deepEqual(
		module
			.getRecentTaskCards(snapshot.recent_tasks)
			.map((task: { task_id: string }) => task.task_id),
		["at-1", "at-2", "og-1"],
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot,
			rangeDays: 14,
			onRangeDaysChange: () => {},
		}),
	);

	assert.match(markup, /href="\/agent-audit\/at-1"/);
	assert.match(markup, /href="\/agent-audit\/at-2"/);
	assert.match(markup, /href="\/tasks\/static"/);
	assert.match(markup, /Alpha Gateway/);
	assert.match(markup, /Beta API/);
	assert.match(markup, /Gamma Portal/);
	assert.match(markup, /Alpha Gateway[\s\S]*智能审计[\s\S]*进行/);
	assert.match(markup, /Beta API[\s\S]*智能审计[\s\S]*完成/);
	assert.match(markup, /Gamma Portal[\s\S]*静态审计[\s\S]*异常/);
	assert.match(markup, /cyber-badge cyber-badge-muted/);
	assert.match(markup, /cyber-badge shrink-0 cyber-badge-primary/);
	assert.match(markup, /cyber-badge shrink-0 cyber-badge-info/);
	assert.match(markup, /cyber-badge shrink-0 cyber-badge-danger/);
	assert.match(markup, /Delta PHP/);
	assert.match(markup, /Echo Console/);
	assert.doesNotMatch(markup, /h-2 rounded-full bg-muted\/70/);
});

test("DashboardCommandCenter maps recent task statuses to dashboard labels", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.equal(module.normalizeRecentTaskStatusLabel("completed"), "完成");
	assert.equal(module.normalizeRecentTaskStatusLabel("running"), "进行");
	assert.equal(module.normalizeRecentTaskStatusLabel("pending"), "进行");
	assert.equal(module.normalizeRecentTaskStatusLabel("interrupted"), "中断");
	assert.equal(module.normalizeRecentTaskStatusLabel("cancelled"), "中断");
	assert.equal(module.normalizeRecentTaskStatusLabel("failed"), "异常");
});

test("DashboardCommandCenter maps recent task badge classes to cyber badge tones", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.equal(
		module.getRecentTaskTypeBadgeClassName("智能审计"),
		"cyber-badge-primary",
	);
	assert.equal(
		module.getRecentTaskTypeBadgeClassName("静态审计"),
		"cyber-badge-info",
	);
	assert.equal(
		module.getRecentTaskProgressBadgeClassName("completed"),
		"cyber-badge-success",
	);
	assert.equal(
		module.getRecentTaskProgressBadgeClassName("running"),
		"cyber-badge-info",
	);
	assert.equal(
		module.getRecentTaskProgressBadgeClassName("cancelled"),
		"cyber-badge-warning",
	);
	assert.equal(
		module.getRecentTaskProgressBadgeClassName("failed"),
		"cyber-badge-danger",
	);
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

test("DashboardCommandCenter keeps task status tooltip counts visible even when all subtype counts are zero", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.task_status_breakdown = {
		pending: 0,
		running: 1,
		completed: 0,
		failed: 0,
		interrupted: 0,
		cancelled: 0,
	};
	snapshot.task_status_by_scan_type.running = {
		static: 0,
		intelligent: 0,
	};

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot,
			rangeDays: 14,
			onRangeDaysChange: () => {},
		}),
	);

	assert.match(markup, /查看智能审计任务状态细分/);
});

test("DashboardCommandCenter uses compact chart spacing constants", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.equal(module.HORIZONTAL_STATS_AXIS_FONT_SIZE, 13);
	assert.equal(module.HORIZONTAL_STATS_LABEL_FONT_SIZE, 12);
	assert.equal(module.HORIZONTAL_STATS_Y_AXIS_MIN_WIDTH, 68);
	assert.equal(module.HORIZONTAL_STATS_Y_AXIS_MAX_WIDTH, 96);
	assert.equal(module.HORIZONTAL_STATS_BAR_SIZE, 9);
	assert.equal(module.HORIZONTAL_STATS_ROW_HEIGHT, 34);
	assert.equal(module.HORIZONTAL_STATS_BAR_CATEGORY_GAP, 2);
	assert.deepEqual(module.HORIZONTAL_STATS_CHART_MARGIN, {
		top: 4,
		right: 16,
		left: 4,
		bottom: 4,
	});
	assert.equal(
		module.HORIZONTAL_STATS_META_ROW_CLASSNAME,
		"mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between",
	);
	assert.equal(
		module.HORIZONTAL_STATS_META_LEGEND_CLASSNAME,
		"flex flex-wrap justify-start gap-2 sm:justify-end",
	);
	assert.equal(
		module.TOP_STATS_GRID_CLASSNAME,
		"grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5",
	);
	assert.equal(
		module.DASHBOARD_MAIN_GRID_CLASSNAME,
		"grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(360px,28rem)] xl:min-h-0 xl:flex-1",
	);
	assert.equal(
		module.DASHBOARD_CHART_AREA_GRID_CLASSNAME,
		"grid min-w-0 gap-4 xl:min-h-0",
	);
	assert.equal(
		module.DASHBOARD_VIEW_RAIL_CLASSNAME,
		"rounded-sm border border-border bg-card p-2 text-card-foreground shadow-sm",
	);
	assert.equal(
		module.DASHBOARD_VIEW_RAIL_LIST_CLASSNAME,
		"grid gap-2 sm:grid-cols-2 xl:grid-cols-5",
	);
});

test("DashboardCommandCenter keeps task sidebar right while chart rail sits above chart", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot: createSnapshotFixture(),
			rangeDays: 14,
			onRangeDaysChange: () => {},
		}),
	);

	assert.match(
		markup,
		/lg:grid-cols-\[minmax\(0,1fr\)_minmax\(360px,28rem\)\]/,
	);
	assert.match(
		markup,
		/grid min-w-0 gap-4 xl:min-h-0/,
	);
	assert.match(markup, /sm:grid-cols-2 xl:grid-cols-5/);
	assert.doesNotMatch(
		markup,
		/xl:grid-cols-\[minmax\(11rem,14rem\)_minmax\(0,1fr\)\]/,
	);
	assert.doesNotMatch(markup, /xl:grid-cols-\[260px_minmax\(0,1fr\)_340px\]/);
	assert.doesNotMatch(
		markup,
		/xl:grid-cols-\[calc\(\(100%-4rem\)\/5\)_minmax\(0,1fr\)_calc\(\(100%-4rem\)\/5\)\]/,
	);
	assert.match(markup, /xl:grid-cols-5/);
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
	assert.deepEqual(
		module.getHorizontalStatsXAxisProps("vulnerability-types", [
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
		]).ticks,
		[0, 5, 10, 15],
	);
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

test("project-risk tooltip formatter returns severity-specific labels", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.deepEqual(
		module.formatHorizontalStatsTooltipValue("project-risk", 3, "严重"),
		["3", "严重漏洞数量"],
	);
	assert.deepEqual(
		module.formatHorizontalStatsTooltipValue("project-risk", 7, "高危"),
		["7", "高危漏洞数量"],
	);
	assert.deepEqual(
		module.formatHorizontalStatsTooltipValue("language-risk", 28, "数量"),
		["28", "数量"],
	);
});

test("recent task title formatter strips the scan type prefix and preserves bare project names", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const [agentTask, intelligentTask, staticTask] =
		createSnapshotFixture().recent_tasks;

	assert.equal(module.getRecentTaskProjectTitle(agentTask), "Alpha Gateway");
	assert.equal(module.getRecentTaskProjectTitle(intelligentTask), "Beta API");
	assert.equal(module.getRecentTaskProjectTitle(staticTask), "Gamma Portal");
	assert.equal(
		module.getRecentTaskProjectTitle({
			...staticTask,
			title: "Standalone Project",
		}),
		"Standalone Project",
	);
});

test("DashboardCommandCenter renders full-card recent task links with explicit assistive labels", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot: createSnapshotFixture(),
			rangeDays: 14,
			onRangeDaysChange: () => {},
		}),
	);

	assert.match(markup, /aria-label="查看 Alpha Gateway 详情"/);
	assert.match(markup, /aria-label="查看 Beta API 详情"/);
	assert.match(markup, /aria-label="查看 Gamma Portal 详情"/);
});

test("recent task cards use a fixed three-item limit", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const tasks = createSnapshotFixture().recent_tasks;

	assert.equal(module.DASHBOARD_RECENT_TASKS_LIMIT, 3);
	assert.deepEqual(module.getRecentTaskCards([]), []);
	assert.deepEqual(
		module.getRecentTaskCards(tasks.slice(0, 1)),
		tasks.slice(0, 1),
	);
	assert.deepEqual(module.getRecentTaskCards(tasks), tasks.slice(0, 3));
});
