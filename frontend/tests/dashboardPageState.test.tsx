import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { DashboardSnapshotResponse } from "../src/shared/types/index.ts";

globalThis.React = React;

async function importOrFail<TModule = Record<string, unknown>>(
	relativePath: string,
): Promise<TModule> {
	try {
		return (await import(relativePath)) as TModule;
	} catch (error) {
		assert.fail(
			`expected dashboard state module ${relativePath} to exist: ${
				error instanceof Error ? error.message : String(error)
			}`,
		);
	}
}

function createEmptySnapshot(): DashboardSnapshotResponse {
	return {
		generated_at: "",
		total_scan_duration_ms: 0,
		scan_runs: [],
		vulns: [],
		rule_confidence: [],
		rule_confidence_by_language: [],
		cwe_distribution: [],
		summary: {
			total_projects: 0,
			current_effective_findings: 0,
			current_verified_findings: 0,
			total_model_tokens: 0,
			false_positive_rate: 0,
			scan_success_rate: 0,
			avg_scan_duration_ms: 0,
			window_scanned_projects: 0,
			window_new_effective_findings: 0,
			window_verified_findings: 0,
			window_false_positive_rate: 0,
			window_scan_success_rate: 0,
			window_avg_scan_duration_ms: 0,
		},
		daily_activity: [],
		verification_funnel: {
			raw_findings: 0,
			effective_findings: 0,
			verified_findings: 0,
			false_positive_count: 0,
		},
		task_status_breakdown: {
			pending: 0,
			running: 0,
			completed: 0,
			failed: 0,
			interrupted: 0,
			cancelled: 0,
		},
		task_status_by_scan_type: {
			pending: { static: 0, intelligent: 0 },
			running: { static: 0, intelligent: 0 },
			completed: { static: 0, intelligent: 0 },
			failed: { static: 0, intelligent: 0 },
			interrupted: { static: 0, intelligent: 0 },
			cancelled: { static: 0, intelligent: 0 },
		},
		engine_breakdown: [],
		project_hotspots: [],
		language_risk: [],
		recent_tasks: [],
		project_risk_distribution: [],
		verified_vulnerability_types: [],
		static_engine_rule_totals: [],
		language_loc_distribution: [],
	};
}

function createSnapshotWithContent() {
	const snapshot = createEmptySnapshot();
	snapshot.summary.total_projects = 2;
	snapshot.project_hotspots = [
		{
			project_id: "p1",
			project_name: "Alpha",
			risk_score: 8,
			scan_runs_window: 1,
			effective_findings: 2,
			verified_findings: 1,
			false_positive_rate: 0,
			dominant_language: "TypeScript",
			last_scan_at: "2026-03-16T03:00:00.000Z",
			top_engine: "opengrep",
		},
	];
	return snapshot;
}

test("dashboard page state renders a blocking error when first load fails without snapshot data", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardPageState.tsx",
	);

	const state = module.resolveDashboardPageState({
		loading: false,
		error: "加载仪表盘快照失败",
		snapshot: createEmptySnapshot(),
	});

	assert.equal(state.variant, "blocking-error");

	const markup = renderToStaticMarkup(
		createElement(module.DashboardPageFeedback, {
			state,
			onRetry: () => {},
		}),
	);

	assert.match(markup, /仪表盘数据加载失败/);
	assert.match(markup, /加载仪表盘快照失败/);
	assert.match(markup, /重试加载/);
});

test("dashboard page state keeps content visible and shows an inline alert when refresh fails", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardPageState.tsx",
	);

	const state = module.resolveDashboardPageState({
		loading: false,
		error: "最新数据刷新失败",
		snapshot: createSnapshotWithContent(),
	});

	assert.equal(state.variant, "inline-error");

	const markup = renderToStaticMarkup(
		createElement(module.DashboardPageFeedback, {
			state,
			onRetry: () => {},
		}),
	);

	assert.match(markup, /最新数据刷新失败/);
	assert.match(markup, /当前展示的是上次成功同步的数据/);
	assert.match(markup, /重试加载/);
});

test("dashboard page state clears the error UI after a successful load", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardPageState.tsx",
	);

	const state = module.resolveDashboardPageState({
		loading: false,
		error: null,
		snapshot: createSnapshotWithContent(),
	});

	assert.equal(state.variant, "idle");
});

test("dashboard page state ignores cwe buckets that only contain zero findings", async () => {
	const module = await importOrFail<any>(
		"../src/features/dashboard/components/DashboardPageState.tsx",
	);

	const snapshot = createEmptySnapshot();
	snapshot.cwe_distribution = [
		{
			cwe_id: "CWE-79",
			cwe_name: "跨站脚本",
			total_findings: 0,
			opengrep_findings: 0,
			agent_findings: 0,
			bandit_findings: 0,
		},
	];

	assert.equal(module.hasDashboardSnapshotContent(snapshot), false);

	const state = module.resolveDashboardPageState({
		loading: false,
		error: "加载仪表盘快照失败",
		snapshot,
	});

	assert.equal(state.variant, "blocking-error");
});

test("dashboard snapshot consumers can tolerate older payloads without task_status_by_scan_type", async () => {
	const source = await importOrFail<any>("../src/pages/Dashboard.tsx");
	const snapshot = createSnapshotWithContent() as Record<string, unknown>;
	delete snapshot.task_status_by_scan_type;

	const normalized = source.normalizeSnapshot(snapshot);

	assert.deepEqual(normalized.task_status_by_scan_type.running, {
		static: 0,
		intelligent: 0,
	});
	assert.deepEqual(normalized.task_status_by_scan_type.completed, {
		static: 0,
		intelligent: 0,
	});
});
