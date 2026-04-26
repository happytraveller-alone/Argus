import test from "node:test";
import assert from "node:assert/strict";

import { normalizeStaticAnalysisSeverity } from "../src/shared/utils/staticAnalysisSeverity.ts";

test("normalizeStaticAnalysisSeverity maps detail-page severity values", () => {
	assert.equal(normalizeStaticAnalysisSeverity("CRITICAL"), "HIGH");
	assert.equal(normalizeStaticAnalysisSeverity("HIGH"), "MEDIUM");
	assert.equal(normalizeStaticAnalysisSeverity("ERROR"), "LOW");
	assert.equal(normalizeStaticAnalysisSeverity("WARNING"), "LOW");
	assert.equal(normalizeStaticAnalysisSeverity("MEDIUM"), "LOW");
	assert.equal(normalizeStaticAnalysisSeverity("INFO"), null);
	assert.equal(normalizeStaticAnalysisSeverity("LOW"), null);
	assert.equal(normalizeStaticAnalysisSeverity(undefined), null);
});
