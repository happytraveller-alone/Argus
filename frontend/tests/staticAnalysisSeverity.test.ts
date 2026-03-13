import test from "node:test";
import assert from "node:assert/strict";

import {
	normalizeStaticAnalysisSeverity,
} from "../src/shared/utils/staticAnalysisSeverity.ts";

test("normalizeStaticAnalysisSeverity maps detail-page severity values", () => {
	assert.equal(normalizeStaticAnalysisSeverity("CRITICAL"), "CRITICAL");
	assert.equal(normalizeStaticAnalysisSeverity("HIGH"), "HIGH");
	assert.equal(normalizeStaticAnalysisSeverity("ERROR"), "MEDIUM");
	assert.equal(normalizeStaticAnalysisSeverity("WARNING"), "MEDIUM");
	assert.equal(normalizeStaticAnalysisSeverity("MEDIUM"), "MEDIUM");
	assert.equal(normalizeStaticAnalysisSeverity("INFO"), "LOW");
	assert.equal(normalizeStaticAnalysisSeverity(undefined), "LOW");
});
