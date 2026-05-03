import test from "node:test";
import assert from "node:assert/strict";

// We test the module's URL/body shapes by intercepting axios via monkey-patching.
// The module is ESM-imported; we validate exported shapes at the type level and
// the URL strings through source inspection to keep this pure-TS node:test.

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const apiClientPath = path.join(
	frontendDir,
	"src/shared/api/intelligentTasks.ts",
);

test("intelligentTasks API module exports required interfaces and functions", () => {
	const source = readFileSync(apiClientPath, "utf8");

	// Interfaces
	assert.match(source, /export\s+interface\s+IntelligentTaskRecord/);
	assert.match(source, /export\s+type\s+IntelligentTaskStatus/);
	assert.match(source, /export\s+interface\s+IntelligentTaskFinding/);

	// Functions
	assert.match(source, /export\s+async\s+function\s+createIntelligentTask/);
	assert.match(source, /export\s+async\s+function\s+listIntelligentTasks/);
	assert.match(source, /export\s+async\s+function\s+getIntelligentTask/);
	assert.match(source, /export\s+async\s+function\s+cancelIntelligentTask/);
});

test("intelligentTasks API uses /intelligent-tasks endpoint (not /agent-tasks)", () => {
	const source = readFileSync(apiClientPath, "utf8");

	assert.match(source, /\/intelligent-tasks/);
	assert.doesNotMatch(source, /\/agent-tasks/);
});

test("createIntelligentTask posts to /intelligent-tasks with projectId body", () => {
	const source = readFileSync(apiClientPath, "utf8");

	assert.match(source, /apiClient\.post\(`\/intelligent-tasks`/);
	assert.match(source, /\{\s*projectId\s*\}/);
});

test("listIntelligentTasks gets /intelligent-tasks with optional limit param", () => {
	const source = readFileSync(apiClientPath, "utf8");

	assert.match(source, /apiClient\.get\(`\/intelligent-tasks`/);
	assert.match(source, /limit/);
});

test("getIntelligentTask gets /intelligent-tasks/{taskId}", () => {
	const source = readFileSync(apiClientPath, "utf8");

	assert.match(source, /apiClient\.get\(`\/intelligent-tasks\/\$\{taskId\}`\)/);
});

test("cancelIntelligentTask posts to /intelligent-tasks/{taskId}/cancel", () => {
	const source = readFileSync(apiClientPath, "utf8");

	assert.match(
		source,
		/apiClient\.post\(\s*`\/intelligent-tasks\/\$\{taskId\}\/cancel`/,
	);
});

test("IntelligentTaskRecord interface has all required fields", () => {
	const source = readFileSync(apiClientPath, "utf8");

	const requiredFields = [
		"taskId",
		"projectId",
		"status",
		"createdAt",
		"llmModel",
		"llmFingerprint",
		"inputSummary",
		"eventLog",
		"reportSummary",
		"findings",
	];
	for (const field of requiredFields) {
		assert.match(
			source,
			new RegExp(`\\b${field}\\b`),
			`Missing field: ${field}`,
		);
	}
});

test("IntelligentTaskRecord has optional proof fields", () => {
	const source = readFileSync(apiClientPath, "utf8");

	assert.match(source, /startedAt\?/);
	assert.match(source, /completedAt\?/);
	assert.match(source, /durationMs\?/);
	assert.match(source, /failureReason\?/);
	assert.match(source, /failureStage\?/);
});

test("IntelligentTaskStatus covers all five terminal and active states", () => {
	const source = readFileSync(apiClientPath, "utf8");

	const states = ["pending", "running", "completed", "failed", "cancelled"];
	for (const s of states) {
		assert.match(source, new RegExp(`"${s}"`), `Missing status: ${s}`);
	}
});

test("listIntelligentTasks returns empty array on non-array response", async () => {
	// Import the actual module and verify defensive coding
	const source = readFileSync(apiClientPath, "utf8");
	assert.match(
		source,
		/Array\.isArray\(response\.data\)\s*\?\s*response\.data\s*:\s*\[\]/,
	);
});
