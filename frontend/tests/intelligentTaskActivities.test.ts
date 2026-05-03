import test from "node:test";
import assert from "node:assert/strict";

import {
	mapIntelligentStatus,
	toIntelligentTaskActivity,
} from "../src/features/tasks/services/intelligentTaskActivities";
import type {
	IntelligentTaskFinding,
	IntelligentTaskRecord,
	IntelligentTaskStatus,
} from "../src/shared/api/intelligentTasks";

const baseRecord: IntelligentTaskRecord = {
	taskId: "tsk-001",
	projectId: "proj-x",
	projectName: "Backend Project",
	status: "pending",
	createdAt: "2026-05-03T00:00:00Z",
	llmModel: "claude-opus",
	llmFingerprint: "fp-1",
	inputSummary: "",
	eventLog: [],
	reportSummary: "",
	findings: [],
};

test("mapIntelligentStatus is identity for all 5 statuses", () => {
	const all: IntelligentTaskStatus[] = [
		"pending",
		"running",
		"completed",
		"failed",
		"cancelled",
	];
	for (const status of all) {
		assert.equal(mapIntelligentStatus(status), status);
		const item = toIntelligentTaskActivity({ ...baseRecord, status });
		assert.equal(item.status, status);
	}
});

test("toIntelligentTaskActivity preserves kind and sourceMode invariants", () => {
	const item = toIntelligentTaskActivity(baseRecord);
	assert.equal(item.kind, "intelligent_audit");
	assert.equal(item.sourceMode, "intelligent");
});

test("toIntelligentTaskActivity sets cancelTarget.mode === 'intelligent'", () => {
	const item = toIntelligentTaskActivity(baseRecord);
	assert.deepEqual(item.cancelTarget, {
		mode: "intelligent",
		taskId: "tsk-001",
	});
});

test("toIntelligentTaskActivity uses /agent-audit/{taskId} route shape", () => {
	const item = toIntelligentTaskActivity(baseRecord);
	assert.equal(item.route, "/agent-audit/tsk-001");
});

test("toIntelligentTaskActivity buckets severities and ignores unknown", () => {
	const findings: IntelligentTaskFinding[] = [
		{ id: "f1", severity: "critical", summary: "", evidence: "" },
		{ id: "f2", severity: "High", summary: "", evidence: "" },
		{ id: "f3", severity: "medium", summary: "", evidence: "" },
		{ id: "f4", severity: "low", summary: "", evidence: "" },
		{ id: "f5", severity: "info", summary: "", evidence: "" },
		{ id: "f6", severity: "MEDIUM", summary: "", evidence: "" },
	];
	const item = toIntelligentTaskActivity({ ...baseRecord, findings });
	assert.deepEqual(item.agentFindingStats, {
		critical: 1,
		high: 1,
		medium: 2,
		low: 1,
		total: 6,
	});
});

test("toIntelligentTaskActivity passes optional fields through with null fallback", () => {
	const item = toIntelligentTaskActivity(baseRecord);
	assert.equal(item.startedAt, null);
	assert.equal(item.completedAt, null);
	assert.equal(item.durationMs, null);
	assert.equal(item.projectName, "Backend Project");

	const richer = toIntelligentTaskActivity(
		{
			...baseRecord,
			projectName: "Backend Rich Project",
			startedAt: "2026-05-03T00:01:00Z",
			completedAt: "2026-05-03T00:02:00Z",
			durationMs: 60000,
		},
	);
	assert.equal(richer.projectName, "Backend Rich Project");
	assert.equal(richer.startedAt, "2026-05-03T00:01:00Z");
	assert.equal(richer.completedAt, "2026-05-03T00:02:00Z");
	assert.equal(richer.durationMs, 60000);
});

test("toIntelligentTaskActivity does not fall back to displaying project id", () => {
	const item = toIntelligentTaskActivity({
		...baseRecord,
		projectId: "raw-project-id",
		projectName: null,
	});
	assert.equal(item.projectName, "-");
});
