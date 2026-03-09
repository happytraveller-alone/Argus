import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolvePreferredModelStats } from "../src/components/system/llmModelStatsSummary.ts";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function read(relativePath: string) {
	return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

test("uses loading state before online stats arrive", () => {
	const result = resolvePreferredModelStats({
		shouldPreferOnlineStats: true,
		staticStats: {
			availableModelCount: 4,
			availableModelMetadataCount: 4,
		},
		cachedOnlineStats: null,
		fetchState: "loading",
	});

	assert.equal(result.modelStatsStatus, "loading");
	assert.equal(result.modelStatsSource, "none");
	assert.equal(result.availableModelCount, 0);
	assert.equal(result.availableModelMetadataCount, 0);
});

test("keeps last online stats after fetch failure for same signature", () => {
	const result = resolvePreferredModelStats({
		shouldPreferOnlineStats: true,
		staticStats: {
			availableModelCount: 4,
			availableModelMetadataCount: 4,
		},
		cachedOnlineStats: {
			availableModelCount: 19,
			availableModelMetadataCount: 7,
		},
		fetchState: "failed",
	});

	assert.equal(result.modelStatsStatus, "cached_online");
	assert.equal(result.modelStatsSource, "cache");
	assert.equal(result.availableModelCount, 19);
	assert.equal(result.availableModelMetadataCount, 7);
});

test("shows empty state when online stats are preferred but never succeeded", () => {
	const result = resolvePreferredModelStats({
		shouldPreferOnlineStats: true,
		staticStats: {
			availableModelCount: 4,
			availableModelMetadataCount: 4,
		},
		cachedOnlineStats: null,
		fetchState: "failed",
	});

	assert.equal(result.modelStatsStatus, "empty");
	assert.equal(result.modelStatsSource, "none");
	assert.equal(result.availableModelCount, 0);
	assert.equal(result.availableModelMetadataCount, 0);
});

test("falls back to static stats when online fetch is not preferred", () => {
	const result = resolvePreferredModelStats({
		shouldPreferOnlineStats: false,
		staticStats: {
			availableModelCount: 4,
			availableModelMetadataCount: 612,
		},
		cachedOnlineStats: {
			availableModelCount: 19,
			availableModelMetadataCount: 7,
		},
		fetchState: "online",
	});

	assert.equal(result.modelStatsStatus, "static");
	assert.equal(result.modelStatsSource, "static");
	assert.equal(result.availableModelCount, 4);
	assert.equal(result.availableModelMetadataCount, 612);
});

test("smart engine page removes metadata subtitle from the model stats card", () => {
	const content = read("src/pages/ScanConfigIntelligentEngine.tsx");

	assert.doesNotMatch(
		content,
		/元数据\s*\{summary\.availableModelMetadataCount\}/,
		"model stats card should no longer render metadata/support subtitle",
	);
});
