import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const dashboardPagePath = path.join(frontendDir, "src/pages/Dashboard.tsx");

test("Dashboard page uses a desktop single-screen shell and no longer reserves 1600px deferred height", () => {
	const source = readFileSync(dashboardPagePath, "utf8");

	assert.match(
		source,
		/className="min-h-screen bg-background px-6 pb-6 pt-0 font-mono relative xl:flex xl:h-\[100dvh\] xl:min-h-0 xl:flex-col xl:overflow-hidden"/,
	);
	assert.match(source, /className="xl:min-h-0 xl:flex-1"/);
	assert.doesNotMatch(source, /minHeight=\{1600\}/);
});
