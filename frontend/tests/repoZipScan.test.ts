import test from "node:test";
import assert from "node:assert/strict";

import { validateZipFile } from "../src/features/projects/services/repoZipScan.ts";

test("validateZipFile accepts newly supported tar.xz and zst archives", () => {
	assert.deepEqual(
		validateZipFile({ name: "demo.tar.xz", size: 1024 } as File),
		{ valid: true },
	);
	assert.deepEqual(
		validateZipFile({ name: "demo.zst", size: 1024 } as File),
		{ valid: true },
	);
});

test("validateZipFile rejects unsupported archive extensions", () => {
	const result = validateZipFile({ name: "demo.iso", size: 1024 } as File);
	assert.equal(result.valid, false);
	assert.match(result.error || "", /tar\.xz/);
	assert.match(result.error || "", /zst/);
});
