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

function extractCssRule(source: string, selector: string) {
	const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	const match = source.match(new RegExp(`${escapedSelector}\\s*\\{(?<body>[^}]+)\\}`));
	return match?.groups?.body ?? "";
}

test("global grid background utilities render as solid background", () => {
	const source = readSource("src/assets/styles/globals.css");

	for (const selector of [".cyber-grid", ".cyber-grid-subtle", ".home-hero-grid"]) {
		const rule = extractCssRule(source, selector);

		assert.match(rule, /background:\s*hsl\(var\(--background\)\)/);
		assert.match(rule, /background-image:\s*none/);
		assert.doesNotMatch(rule, /linear-gradient/);
		assert.doesNotMatch(rule, /background-size:/);
	}
});
