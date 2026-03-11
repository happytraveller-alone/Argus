import test from "node:test";
import assert from "node:assert/strict";

import {
	buildAgentFindingDetailNavigation,
	resolveFindingDetailBackTarget,
} from "../src/shared/utils/findingRoute.ts";

test("buildAgentFindingDetailNavigation returns route and prefers history back for task detail flows", () => {
	const result = buildAgentFindingDetailNavigation({
		taskId: "task-1",
		findingId: "finding-2",
		currentRoute: "/agent-audit/task-1?returnTo=%2Ftasks%2Fhybrid&detailType=finding&detailId=finding-2",
	});

	assert.equal(
		result.route,
		"/finding-detail/agent/task-1/finding-2?returnTo=%2Fagent-audit%2Ftask-1%3FreturnTo%3D%252Ftasks%252Fhybrid",
	);
	assert.deepEqual(result.state, {
		fromTaskDetail: true,
		preferHistoryBack: true,
	});
});

test("buildAgentFindingDetailNavigation can carry a transient false-positive snapshot", () => {
	const result = buildAgentFindingDetailNavigation({
		taskId: "task-1",
		findingId: "finding-fp",
		currentRoute: "/agent-audit/task-1",
		snapshot: {
			id: "finding-fp",
			task_id: "task-1",
			vulnerability_type: "hardcoded_secret",
			severity: "low",
			title: "示例文件误报",
			description: "示例描述",
			file_path: "fixtures/demo.ts",
			line_start: 7,
			line_end: 7,
			code_snippet: null,
			code_context: null,
			context_start_line: null,
			context_end_line: null,
			status: "false_positive",
			is_verified: false,
			reachability: "unreachable",
			authenticity: "false_positive",
			verification_evidence: "示例配置模板，不参与实际部署",
			has_poc: false,
			poc_code: null,
			suggestion: null,
			fix_code: null,
			ai_explanation: null,
			ai_confidence: null,
			created_at: "2026-03-11T00:00:00Z",
			verification_todo_id: "todo-1",
			verification_fingerprint: "fp-1",
		},
	});

	assert.equal(result.state.agentFindingSnapshot?.id, "finding-fp");
	assert.equal(result.state.agentFindingSnapshot?.verification_todo_id, "todo-1");
	assert.equal(
		result.state.agentFindingSnapshot?.verification_evidence,
		"示例配置模板，不参与实际部署",
	);
});

test("resolveFindingDetailBackTarget prefers history only when navigation state opts in", () => {
	assert.equal(
		resolveFindingDetailBackTarget({
			returnTo: "/agent-audit/task-1?returnTo=%2Ftasks%2Fintelligent",
			hasHistory: true,
			state: { fromTaskDetail: true, preferHistoryBack: true },
		}),
		-1,
	);

	assert.equal(
		resolveFindingDetailBackTarget({
			returnTo: "/agent-audit/task-1?returnTo=%2Ftasks%2Fintelligent",
			hasHistory: true,
			state: null,
		}),
		"/agent-audit/task-1?returnTo=%2Ftasks%2Fintelligent",
	);

	assert.equal(
		resolveFindingDetailBackTarget({
			returnTo: "",
			hasHistory: true,
			state: null,
		}),
		-1,
	);

	assert.equal(
		resolveFindingDetailBackTarget({
			returnTo: "",
			hasHistory: false,
			state: null,
		}),
		"/dashboard",
	);
});
