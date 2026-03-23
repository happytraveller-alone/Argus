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
		generated_at: "2026-03-16T03:00:00.000Z",
		total_scan_duration_ms: 90061000,
		scan_runs: [],
		vulns: [],
		rule_confidence: [],
		rule_confidence_by_language: [
			{ language: "TypeScript", high_count: 1, medium_count: 0 },
			{ language: "Python", high_count: 0, medium_count: 1 },
		],
		cwe_distribution: [
			{
				cwe_id: "CWE-79",
				cwe_name: "跨站脚本",
				total_findings: 3,
				opengrep_findings: 2,
				agent_findings: 1,
				bandit_findings: 0,
			},
			{
				cwe_id: "CWE-89",
				cwe_name: "SQL 注入",
				total_findings: 2,
				opengrep_findings: 1,
				agent_findings: 1,
				bandit_findings: 0,
			},
		],
		summary: {
			total_projects: 2,
			current_effective_findings: 9,
			current_verified_findings: 5,
			false_positive_rate: 0.2307,
			scan_success_rate: 0.8889,
			avg_scan_duration_ms: 819,
			window_scanned_projects: 2,
			window_new_effective_findings: 8,
			window_verified_findings: 5,
			window_false_positive_rate: 0.2727,
			window_scan_success_rate: 1,
			window_avg_scan_duration_ms: 825,
		},
		daily_activity: [
			{
				date: "2026-03-14",
				completed_scans: 2,
				agent_findings: 0,
				opengrep_findings: 0,
				gitleaks_findings: 2,
				bandit_findings: 1,
				phpstan_findings: 0,
			},
			{
				date: "2026-03-15",
				completed_scans: 3,
				agent_findings: 1,
				opengrep_findings: 2,
				gitleaks_findings: 0,
				bandit_findings: 0,
				phpstan_findings: 2,
			},
		],
		verification_funnel: {
			raw_findings: 11,
			effective_findings: 8,
			verified_findings: 5,
			false_positive_count: 3,
		},
		task_status_breakdown: {
			pending: 0,
			running: 1,
			completed: 8,
			failed: 1,
			interrupted: 0,
			cancelled: 0,
		},
		engine_breakdown: [
			{
				engine: "agent",
				completed_scans: 1,
				effective_findings: 1,
				verified_findings: 1,
				false_positive_count: 1,
				avg_scan_duration_ms: 1000,
				success_rate: 1,
			},
			{
				engine: "opengrep",
				completed_scans: 1,
				effective_findings: 2,
				verified_findings: 1,
				false_positive_count: 1,
				avg_scan_duration_ms: 1200,
				success_rate: 1,
			},
		],
		project_hotspots: [
			{
				project_id: "p1",
				project_name: "Alpha",
				risk_score: 32,
				scan_runs_window: 4,
				effective_findings: 7,
				verified_findings: 4,
				false_positive_rate: 0,
				dominant_language: "TypeScript",
				last_scan_at: "2026-03-15T03:00:00.000Z",
				top_engine: "opengrep",
			},
			{
				project_id: "p2",
				project_name: "Beta",
				risk_score: 12.5,
				scan_runs_window: 2,
				effective_findings: 2,
				verified_findings: 1,
				false_positive_rate: 0.6667,
				dominant_language: "Python",
				last_scan_at: "2026-03-16T01:00:00.000Z",
				top_engine: "bandit",
			},
		],
		language_risk: [
			{
				language: "TypeScript",
				project_count: 1,
				loc_number: 700,
				effective_findings: 5,
				verified_findings: 3,
				false_positive_count: 0,
				findings_per_kloc: 7.14,
				rules_high: 1,
				rules_medium: 0,
			},
			{
				language: "PHP",
				project_count: 1,
				loc_number: 300,
				effective_findings: 2,
				verified_findings: 1,
				false_positive_count: 0,
				findings_per_kloc: 6.67,
				rules_high: 1,
				rules_medium: 0,
			},
		],
	};
}

test("DashboardCommandCenter renders the current summary strip and primary panels", async () => {
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

	assert.match(markup, /扫描项目总数/);
	assert.match(markup, /当前发现漏洞/);
	assert.match(markup, /已验证漏洞/);
	// assert.match(markup, /累计扫描时长/);
	assert.match(markup, /累计执行扫描/);
	assert.match(markup, /可挖掘漏洞类型/);
	assert.match(markup, /漏洞态势趋势/);
	assert.match(markup, /任务状态/);
	assert.match(markup, /风险热点项目/);
	// assert.match(markup, /引擎贡献/);
	// assert.match(markup, /语言风险热力/);
	assert.match(markup, /TypeScript/);
	assert.match(markup, /1天 1时 1分 1秒/);
	assert.match(markup, />8</);
	assert.match(markup, />2</);
	assert.match(markup, /过去 14 天内各扫描引擎的有效风险发现和扫描活跃度/);
	assert.doesNotMatch(markup, /text-\[11px\] uppercase tracking-\[0\.28em\] text-slate-400">误报率<\/p>/);
	assert.doesNotMatch(markup, /text-\[11px\] uppercase tracking-\[0\.28em\] text-slate-400">扫描成功率<\/p>/);
	assert.doesNotMatch(markup, /text-\[11px\] uppercase tracking-\[0\.28em\] text-slate-400">平均扫描耗时<\/p>/);
	assert.doesNotMatch(markup, /3 条发现/);
	assert.doesNotMatch(markup, /2 条发现/);
	assert.doesNotMatch(markup, /data-panel="funnel"/);
	assert.doesNotMatch(markup, /data-panel="cwe"/);
});

test("formatCumulativeDuration formats dashboard scan duration with zh units down to seconds", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	assert.equal(module.formatCumulativeDuration(0), "0秒");
	assert.equal(module.formatCumulativeDuration(7050), "7秒");
	assert.equal(module.formatCumulativeDuration(61000), "1分 1秒");
	assert.equal(module.formatCumulativeDuration(3605000), "1时 0分 5秒");
	assert.equal(module.formatCumulativeDuration(90061000), "1天 1时 1分 1秒");
});

test("DashboardCommandCenter keeps the current primary grid order and leaves language risk below the grid", async () => {
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
		/data-layout="primary-grid"[^>]*class="[^"]*grid[^"]*gap-4[^"]*lg:grid-cols-12/,
	);
	assert.match(markup, /data-panel="trend"[^>]*class="[^"]*lg:col-span-7/);
	assert.match(markup, /data-panel="hotspots"[^>]*class="[^"]*lg:col-span-7/);
	assert.match(markup, /data-panel="status"[^>]*class="[^"]*lg:col-span-5/);
	assert.match(markup, /data-panel="engines"[^>]*class="[^"]*lg:col-span-7/);
	assert.match(markup, /data-panel="language-risk"/);

	const trendIndex = markup.indexOf('data-panel="trend"');
	const hotspotsIndex = markup.indexOf('data-panel="hotspots"');
	const statusIndex = markup.indexOf('data-panel="status"');
	const enginesIndex = markup.indexOf('data-panel="engines"');
	const languageRiskIndex = markup.indexOf('data-panel="language-risk"');

	assert.notEqual(trendIndex, -1);
	assert.ok(trendIndex < hotspotsIndex);
	assert.ok(hotspotsIndex < statusIndex);
	assert.ok(statusIndex < enginesIndex);
	assert.ok(enginesIndex < languageRiskIndex);
	assert.equal(markup.indexOf('data-panel="funnel"'), -1);
	assert.equal(markup.indexOf('data-panel="cwe"'), -1);
});

test("DashboardCommandCenter shows empty-state copy when snapshot panels are empty", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.daily_activity = [];
	snapshot.engine_breakdown = [];
	snapshot.project_hotspots = [];
	snapshot.language_risk = [];
	snapshot.cwe_distribution = [];

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot,
			rangeDays: 7,
			onRangeDaysChange: () => {},
		}),
	);

	assert.match(markup, /暂无趋势数据/);
	assert.match(markup, /暂无热点项目/);
	// assert.match(markup, /暂无引擎贡献数据/);
	// assert.match(markup, /暂无语言风险数据/);
	// assert.doesNotMatch(markup, /暂无 CWE 攻击面数据/);
});

test("DashboardCommandCenter no longer renders the legacy cwe panel in the main layout", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);
	const snapshot = createSnapshotFixture();
	snapshot.cwe_distribution = [
		{
			cwe_id: "CWE-79",
			cwe_name: "跨站脚本",
			total_findings: 0,
			opengrep_findings: 0,
			agent_findings: 0,
			bandit_findings: 0,
		},
		{
			cwe_id: "CWE-89",
			cwe_name: "SQL 注入",
			total_findings: -1,
			opengrep_findings: 0,
			agent_findings: 0,
			bandit_findings: 0,
		},
	];

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			snapshot,
			rangeDays: 14,
			onRangeDaysChange: () => {},
		}),
	);

	assert.doesNotMatch(markup, /CWE-79/);
	assert.doesNotMatch(markup, /CWE-89/);
	assert.doesNotMatch(markup, /CWE 攻击面/);
	assert.equal(markup.indexOf('data-panel="cwe"'), -1);
});

test("AttackSurfaceTreemapContent renders tile text from flat treemap node props", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(
			"svg",
			null,
			createElement(module.AttackSurfaceTreemapContent, {
				x: 0,
				y: 0,
				width: 124,
				height: 72,
				fill: "#155e75",
				cweId: "CWE-79",
				cweName: "跨站脚本",
				totalFindings: 3,
				opengrepFindings: 2,
				agentFindings: 1,
				banditFindings: 0,
				name: "CWE-79",
				size: 3,
			}),
		),
	);

	assert.match(markup, /跨站脚本/);
	assert.match(markup, /3 条发现/);
	assert.doesNotMatch(markup, /\srx="/);
	assert.doesNotMatch(markup, /\sry="/);
});

test("AttackSurfaceTreemapTooltipContent uses straight-edge tooltip styling", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardCommandCenter.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.AttackSurfaceTreemapTooltipContent, {
			item: {
				cweId: "CWE-79",
				cweName: "跨站脚本",
				totalFindings: 3,
				opengrepFindings: 2,
				agentFindings: 1,
				banditFindings: 0,
				name: "CWE-79",
				size: 3,
				fill: "#155e75",
			},
		}),
	);

	assert.match(markup, /rounded-none/);
	assert.doesNotMatch(markup, /rounded-2xl/);
	assert.match(markup, /跨站脚本/);
	assert.match(markup, /发现总数：3/);
});
