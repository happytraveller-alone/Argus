import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const frontendDir = process.cwd();
const sourceDir = path.join(frontendDir, "src");
const globalsCssPath = path.join(frontendDir, "src/assets/styles/globals.css");
const tailwindConfigPath = path.join(frontendDir, "tailwind.config.js");

function collectSourceFiles(dir: string): string[] {
	const entries = readdirSync(dir, { withFileTypes: true });
	return entries.flatMap((entry) => {
		const entryPath = path.join(dir, entry.name);
		if (entry.isDirectory()) {
			return collectSourceFiles(entryPath);
		}
		if (/\.(css|ts|tsx)$/.test(entry.name)) {
			return [entryPath];
		}
		return [];
	});
}

test("interactive focus states use flat affordances instead of glow or ring halos", () => {
	const forbiddenPatterns = [
		/focus(?:-visible)?:shadow-focus/g,
		/focus(?:-visible)?:ring(?:-[^\s"'`}]+)?/g,
		/ring-offset(?:-[^\s"'`}]+)?/g,
	];
	const violations = collectSourceFiles(sourceDir).flatMap((filePath) => {
		const source = readFileSync(filePath, "utf8");
		return forbiddenPatterns.flatMap((pattern) =>
			Array.from(source.matchAll(pattern), (match) => ({
				filePath: path.relative(frontendDir, filePath),
				token: match[0],
			})),
		);
	});

	assert.deepEqual(violations, []);
});

test("global focus styling no longer exposes the shadow-focus halo token", () => {
	const globalsCss = readFileSync(globalsCssPath, "utf8");
	const tailwindConfig = readFileSync(tailwindConfigPath, "utf8");

	assert.doesNotMatch(globalsCss, /--shadow-focus/);
	assert.doesNotMatch(globalsCss, /box-shadow:\s*var\(--shadow-focus\)/);
	assert.doesNotMatch(
		globalsCss,
		/:focus(?:-visible)?[\s\S]{0,180}box-shadow\s*:/,
	);
	assert.doesNotMatch(tailwindConfig, /shadow-focus|['"]focus['"]/);
});

test("cyber primary buttons keep selected state flat without blue outer glow", () => {
	const globalsCss = readFileSync(globalsCssPath, "utf8");

	assert.doesNotMatch(
		globalsCss,
		/\.cyber-btn-primary[\s\S]{0,260}0\s+0\s+\d+px\s+rgba\(0,\s*122,\s*204,/,
	);
});
