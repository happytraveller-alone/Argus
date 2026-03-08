import test from "node:test";
import assert from "node:assert/strict";

import {
	accumulateTokenUsage,
	buildFindingTableState,
	buildStatsSummary,
	createTokenUsageAccumulator,
	shouldResetFindingPage,
} from "../src/pages/AgentAudit/detailViewModel.ts";

test("accumulateTokenUsage 聚合 llm_call_complete 并按 sequence 去重", () => {
	const first = createTokenUsageAccumulator();
	const second = accumulateTokenUsage(first, {
		event_type: "llm_call_complete",
		sequence: 11,
		metadata: {
			tokens_input: 120,
			tokens_output: 45,
		},
	});
	const third = accumulateTokenUsage(second, {
		event_type: "llm_call_complete",
		sequence: 11,
		metadata: {
			tokens_input: 999,
			tokens_output: 999,
		},
	});
	const fourth = accumulateTokenUsage(third, {
		event_type: "info",
		sequence: 12,
		metadata: {
			tokens_input: 10,
			tokens_output: 10,
		},
	});
	const fifth = accumulateTokenUsage(fourth, {
		event_type: "llm_call_complete",
		sequence: 13,
		metadata: {
			tokens_input: 80,
			tokens_output: 20,
		},
	});

	assert.deepEqual(
		{
			input: fifth.inputTokens,
			output: fifth.outputTokens,
			total: fifth.totalTokens,
			seen: [...fifth.seenSequences].sort((left, right) => left - right),
		},
		{
			input: 200,
			output: 65,
			total: 265,
			seen: [11, 13],
		},
	);
});

test("buildStatsSummary 在无实时漏洞时回退到任务统计，并把误报算入已验证", () => {
	const summary = buildStatsSummary({
		task: {
			progress_percentage: 62,
			started_at: "2026-03-08T10:00:00.000Z",
			completed_at: "2026-03-08T10:03:00.000Z",
			findings_count: 6,
			verified_count: 2,
			false_positive_count: 1,
			total_iterations: 4,
			tool_calls_count: 9,
		},
		realtimeFindings: [],
		tokenUsage: {
			inputTokens: 300,
			outputTokens: 120,
			totalTokens: 420,
			seenSequences: new Set<number>(),
		},
		now: new Date("2026-03-08T10:04:00.000Z"),
	});

	assert.deepEqual(summary, {
		progressPercent: 62,
		durationMs: 180000,
		findingsTotal: 6,
		findingsVerified: 3,
		findingsPending: 3,
		iterations: 4,
		toolCalls: 9,
		tokensTotal: 420,
		tokensInput: 300,
		tokensOutput: 120,
	});
});

test("buildFindingTableState 按严重度与置信度排序、筛选并分页", () => {
	const state = buildFindingTableState({
		items: [
			{
				id: "low-verified",
				title: "low verified",
				vulnerability_type: "info",
				severity: "low",
				display_severity: "low",
				verification_progress: "verified",
				file_path: "b/file.ts",
				line_start: 10,
				confidence: 0.2,
				is_verified: true,
			},
			{
				id: "high-a",
				title: "sql injection",
				vulnerability_type: "CWE-89",
				severity: "high",
				display_severity: "high",
				verification_progress: "pending",
				file_path: "a/file.ts",
				line_start: 8,
				confidence: 0.8,
				is_verified: false,
			},
			{
				id: "critical-z",
				title: "rce",
				vulnerability_type: "CWE-78",
				severity: "critical",
				display_severity: "critical",
				verification_progress: "pending",
				file_path: "z/file.ts",
				line_start: 2,
				confidence: 0.1,
				is_verified: false,
			},
			{
				id: "high-b",
				title: "auth bypass",
				vulnerability_type: "CWE-287",
				severity: "high",
				display_severity: "high",
				verification_progress: "pending",
				file_path: "b/file.ts",
				line_start: 1,
				confidence: 0.6,
				is_verified: false,
			},
		],
		filters: {
			keyword: "",
			severity: "all",
			verification: "pending",
		},
		page: 2,
		pageSize: 2,
	});

	assert.equal(state.totalRows, 3);
	assert.equal(state.totalPages, 2);
	assert.equal(state.page, 2);
	assert.deepEqual(
		state.rows.map((item) => item.id),
		["high-b"],
	);

	const filtered = buildFindingTableState({
		items: state.allRows,
		filters: {
			keyword: "sql",
			severity: "high",
			verification: "pending",
		},
		page: 9,
		pageSize: 10,
	});

	assert.equal(filtered.page, 1);
	assert.deepEqual(
		filtered.rows.map((item) => item.id),
		["high-a"],
	);
});

test("shouldResetFindingPage 仅在筛选条件变化时返回 true", () => {
	assert.equal(
		shouldResetFindingPage(
			{ keyword: "", severity: "all", verification: "all" },
			{ keyword: "sql", severity: "all", verification: "all" },
		),
		true,
	);
	assert.equal(
		shouldResetFindingPage(
			{ keyword: "sql", severity: "high", verification: "pending" },
			{ keyword: "sql", severity: "high", verification: "pending" },
		),
		false,
	);
});
