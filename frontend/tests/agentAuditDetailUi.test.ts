import test from "node:test";
import assert from "node:assert/strict";

import {
	AGENT_AUDIT_FINDINGS_PAGE_SIZE,
	accumulateTokenUsage,
	buildFindingTableState,
	buildStatsSummary,
	createTokenUsageAccumulator,
	resolveAgentAuditBackTarget,
	resolveAgentAuditDetailTitle,
	shouldResetFindingPage,
} from "../src/pages/AgentAudit/detailViewModel.ts";
import {
	buildAgentFindingDetailRoute,
	sanitizeAgentAuditReturnTo,
} from "../src/shared/utils/findingRoute.ts";

test("resolveAgentAuditDetailTitle 优先按 returnTo 判定智能/混合详情标题", () => {
	assert.equal(
		resolveAgentAuditDetailTitle({
			returnTo: "/tasks/intelligent?openCreate=1",
			name: "混合扫描-智能扫描-demo",
			description: "[HYBRID]混合扫描智能阶段任务",
		}),
		"智能扫描详情",
	);

	assert.equal(
		resolveAgentAuditDetailTitle({
			returnTo: "/tasks/hybrid",
			name: "智能扫描-demo",
			description: "[INTELLIGENT]智能扫描任务",
		}),
		"混合扫描详情",
	);
});

test("resolveAgentAuditDetailTitle 在无 returnTo 时回退到任务元信息，默认智能扫描详情", () => {
	assert.equal(
		resolveAgentAuditDetailTitle({
			returnTo: "",
			name: "混合扫描-智能扫描-demo",
			description: "[HYBRID]混合扫描智能阶段任务",
		}),
		"混合扫描详情",
	);

	assert.equal(
		resolveAgentAuditDetailTitle({
			returnTo: "",
			name: "普通任务",
			description: "",
		}),
		"智能扫描详情",
	);
});

test("resolveAgentAuditBackTarget 优先返回智能/混合列表，否则回退 history 或仪表盘", () => {
	assert.equal(
		resolveAgentAuditBackTarget("/tasks/intelligent?openCreate=1", true),
		"/tasks/intelligent?openCreate=1",
	);
	assert.equal(
		resolveAgentAuditBackTarget("/tasks/hybrid", true),
		"/tasks/hybrid",
	);
	assert.equal(resolveAgentAuditBackTarget("", true), -1);
	assert.equal(resolveAgentAuditBackTarget("", false), "/dashboard");
});

test("sanitizeAgentAuditReturnTo 移除旧详情参数但保留嵌套 returnTo", () => {
	assert.equal(
		sanitizeAgentAuditReturnTo(
			"/agent-audit/task-1?muteToast=1&detailType=finding&detailId=finding-1&returnTo=%2Ftasks%2Fhybrid%3FopenCreate%3D1",
		),
		"/agent-audit/task-1?muteToast=1&returnTo=%2Ftasks%2Fhybrid%3FopenCreate%3D1",
	);
});

test("buildAgentFindingDetailRoute 生成统一缺陷详情链接并附带清洗后的 returnTo", () => {
	assert.equal(
		buildAgentFindingDetailRoute({
			taskId: "task-1",
			findingId: "finding-1",
			currentRoute:
				"/agent-audit/task-1?muteToast=1&detailType=finding&detailId=finding-1&returnTo=%2Ftasks%2Fintelligent",
		}),
		"/finding-detail/agent/task-1/finding-1?returnTo=%2Fagent-audit%2Ftask-1%3FmuteToast%3D1%26returnTo%3D%252Ftasks%252Fintelligent",
	);
});

test("AGENT_AUDIT_FINDINGS_PAGE_SIZE 固定为每页三条", () => {
	assert.equal(AGENT_AUDIT_FINDINGS_PAGE_SIZE, 3);
});

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

test("buildStatsSummary 在无实时漏洞时回退到任务统计，并动态拆分总数、有效数和误报数", () => {
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
		totalFindings: 7,
		effectiveFindings: 6,
		falsePositiveFindings: 1,
		iterations: 4,
		toolCalls: 9,
		tokensTotal: 420,
		tokensInput: 300,
		tokensOutput: 120,
	});
});

test("buildStatsSummary 在有实时漏洞时优先使用实时结果统计总数、有效数和误报数", () => {
	const summary = buildStatsSummary({
		task: {
			progress_percentage: 88,
			findings_count: 99,
			verified_count: 88,
			false_positive_count: 11,
			total_iterations: 7,
			tool_calls_count: 15,
		},
		realtimeFindings: [
			{
				id: "finding-1",
				title: "sql injection",
				vulnerability_type: "sql_injection",
				severity: "high",
				display_severity: "high",
				verification_progress: "pending",
				file_path: "src/a.ts",
				line_start: 8,
				confidence: 0.91,
				is_verified: false,
				authenticity: "confirmed",
			},
			{
				id: "finding-2",
				title: "auth bypass",
				vulnerability_type: "auth_bypass",
				severity: "medium",
				display_severity: "medium",
				verification_progress: "verified",
				file_path: "src/b.ts",
				line_start: 19,
				confidence: 0.76,
				is_verified: true,
				authenticity: "likely",
			},
			{
				id: "finding-fp",
				title: "template secret",
				vulnerability_type: "hardcoded_secret",
				severity: "low",
				display_severity: "invalid",
				verification_progress: "verified",
				file_path: "fixtures/demo.ts",
				line_start: 7,
				confidence: 0.12,
				is_verified: true,
				authenticity: "false_positive",
				detailMode: "false_positive_reason",
			},
		],
		tokenUsage: {
			inputTokens: 0,
			outputTokens: 0,
			totalTokens: 0,
			seenSequences: new Set<number>(),
		},
		now: new Date("2026-03-08T10:04:00.000Z"),
	});

	assert.equal(summary.totalFindings, 3);
	assert.equal(summary.effectiveFindings, 2);
	assert.equal(summary.falsePositiveFindings, 1);
});

test("buildStatsSummary 在有输入输出拆分时以两者求和作为总 Token", () => {
	const summary = buildStatsSummary({
		task: {
			progress_percentage: 50,
			findings_count: 1,
			verified_count: 0,
			false_positive_count: 0,
			total_iterations: 1,
			tool_calls_count: 2,
			tokens_used: 9999,
		},
		realtimeFindings: [],
		tokenUsage: {
			inputTokens: 120,
			outputTokens: 45,
			totalTokens: 9999,
			seenSequences: new Set<number>([1]),
		},
		now: new Date("2026-03-08T10:04:00.000Z"),
	});

	assert.equal(summary.tokensInput, 120);
	assert.equal(summary.tokensOutput, 45);
	assert.equal(summary.tokensTotal, 165);
});

test("buildStatsSummary 在仅有总 Token 无拆分时保留总数并返回空拆分", () => {
	const summary = buildStatsSummary({
		task: {
			progress_percentage: 50,
			findings_count: 1,
			verified_count: 0,
			false_positive_count: 0,
			total_iterations: 1,
			tool_calls_count: 2,
			tokens_used: 420,
		},
		realtimeFindings: [],
		tokenUsage: {
			inputTokens: 0,
			outputTokens: 0,
			totalTokens: 0,
			seenSequences: new Set<number>(),
		},
		now: new Date("2026-03-08T10:04:00.000Z"),
	});

	assert.equal(summary.tokensTotal, 420);
	assert.equal(summary.tokensInput, null);
	assert.equal(summary.tokensOutput, null);
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
