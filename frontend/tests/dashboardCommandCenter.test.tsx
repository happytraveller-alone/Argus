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
		total_scan_duration_ms: 7050,
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

test("DashboardCommandCenter renders the control-center sections and hotspot data", async () => {
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

	assert.match(markup, /漏洞扫描统计/);
	assert.match(markup, /当前有效风险/);
	assert.match(markup, /验证漏斗/);
	assert.match(markup, /任务状态/);
	assert.match(markup, /风险热点项目/);
	assert.match(markup, /语言风险热力/);
	assert.match(markup, /CWE 攻击面/);
	assert.match(markup, /Alpha/);
	assert.match(markup, /Beta/);
	assert.match(markup, /TypeScript/);
	assert.match(markup, /CWE-79/);
	assert.match(markup, />7 天</);
	assert.match(markup, />14 天</);
	assert.match(markup, />30 天</);
});

test("DashboardCommandCenter uses the planned main-grid pairing on large screens", async () => {
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
	assert.match(markup, /data-panel="funnel"[^>]*class="[^"]*lg:col-span-5/);
	assert.match(markup, /data-panel="hotspots"[^>]*class="[^"]*lg:col-span-7/);
	assert.match(markup, /data-panel="status"[^>]*class="[^"]*lg:col-span-5/);
	assert.match(markup, /data-panel="engines"[^>]*class="[^"]*lg:col-span-7/);
	assert.match(markup, /data-panel="language-risk"[^>]*class="[^"]*lg:col-span-5/);

	const trendIndex = markup.indexOf('data-panel="trend"');
	const funnelIndex = markup.indexOf('data-panel="funnel"');
	const hotspotsIndex = markup.indexOf('data-panel="hotspots"');
	const statusIndex = markup.indexOf('data-panel="status"');
	const enginesIndex = markup.indexOf('data-panel="engines"');
	const languageRiskIndex = markup.indexOf('data-panel="language-risk"');
	const cweIndex = markup.indexOf('data-panel="cwe"');

	assert.notEqual(trendIndex, -1);
	assert.ok(trendIndex < funnelIndex);
	assert.ok(funnelIndex < hotspotsIndex);
	assert.ok(hotspotsIndex < statusIndex);
	assert.ok(statusIndex < enginesIndex);
	assert.ok(enginesIndex < languageRiskIndex);
	assert.ok(languageRiskIndex < cweIndex);
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
	assert.match(markup, /暂无语言风险数据/);
	assert.match(markup, /暂无 CWE 攻击面数据/);
});
