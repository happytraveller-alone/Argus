import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);

test("ProjectsTable shrinks header typography and aligns row text with action text", () => {
	const projectsTablePath = path.join(
		frontendDir,
		"src/pages/projects/components/ProjectsTable.tsx",
	);
	const source = readFileSync(projectsTablePath, "utf8");

	assert.match(source, /text-\[14px\] font-semibold uppercase/);
	assert.match(source, /const HEADER_CONTENT_CLASSNAME = "text-\[14px\]"/);
	assert.match(source, /text-center text-\[16px\] text-muted-foreground/);
	assert.match(source, /truncate text-center text-\[16px\] font-semibold/);
	assert.match(source, /justify-center gap-2 text-\[16px\]/);
	assert.doesNotMatch(source, /text-\[15px\] font-semibold uppercase/);
	assert.doesNotMatch(source, /const HEADER_CONTENT_CLASSNAME = "text-\[15px\]"/);
	assert.doesNotMatch(source, /text-center text-\[17px\] text-muted-foreground/);
	assert.doesNotMatch(source, /truncate text-center text-\[18px\] font-semibold/);
});
