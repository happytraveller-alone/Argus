import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const opengrepRulesPath = path.join(frontendDir, "src/pages/OpengrepRules.tsx");

test("scan config rules table opts into column resizing with compressed defaults", () => {
	const source = readFileSync(opengrepRulesPath, "utf8");

	assert.match(source, /enableColumnResizing/);
	assert.match(source, /toolbar={false}/);
	assert.match(source, /tableClassName="w-full"/);
	assert.match(source, /const OPENGREP_RULE_TABLE_HEADER_CLASSNAME = "text-xs tracking-\[0\.12em\]"/);
	assert.match(source, /const OPENGREP_RULE_TABLE_CELL_CLASSNAME = "text-xs"/);
	assert.match(
		source,
		/id: "ruleName"[\s\S]*width: 220,[\s\S]*minWidth: 180,[\s\S]*filterVariant: "text"/,
	);
	assert.match(
		source,
		/id: "actions"[\s\S]*width: 240,[\s\S]*minWidth: 220/,
	);
	assert.doesNotMatch(source, /meta: \{ label: "操作", minWidth: 320 \}/);
});
