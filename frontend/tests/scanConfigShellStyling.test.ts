import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);

function readSource(relativePath: string) {
	return readFileSync(path.join(frontendDir, relativePath), "utf8");
}

test("scan config page shells remove outer cyber frames and glow backgrounds", () => {
	const shellSources = [
		"src/pages/ScanConfigEngines.tsx",
		"src/pages/ScanConfigIntelligentEngine.tsx",
		"src/pages/ScanConfigExternalTools.tsx",
	];

	for (const relativePath of shellSources) {
		const source = readSource(relativePath);
		assert.doesNotMatch(source, /cyber-grid-subtle/);
		assert.doesNotMatch(source, /cyber-card(?:\s|")/);
		assert.doesNotMatch(source, /bg-gradient/);
		assert.doesNotMatch(source, /shadow-\[/);
	}
});

test("embedded OpengrepRules does not render the outer grid background", () => {
	const source = readSource("src/pages/OpengrepRules.tsx");

	assert.match(source, /!\s*embedded\s*&&\s*\(/);
	assert.match(
		source,
		/className=\{`space-y-6 \$\{embedded \? "p-0" : "p-6"\} relative z-10`\}/,
	);
	assert.doesNotMatch(
		source,
		/<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" \/>/,
	);
});
