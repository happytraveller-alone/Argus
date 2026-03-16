import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(testDir, "..");

test("frontend lint script relies on the checked-in TypeScript and Biome steps only", () => {
	const packageJson = JSON.parse(
		fs.readFileSync(path.join(frontendDir, "package.json"), "utf8"),
	) as {
		scripts?: Record<string, string>;
		devDependencies?: Record<string, string>;
	};

	const lintScript = String(packageJson.scripts?.lint || "");

	assert.match(lintScript, /\btsgo -p tsconfig\.check\.json\b/);
	assert.match(
		lintScript,
		/\bbiome lint --only=correctness\/noUndeclaredDependencies src tests scripts\b/,
	);
	assert.equal(lintScript.includes("rm -rf dist"), false);
	assert.equal(lintScript.includes("ast-grep"), false);
	assert.equal(packageJson.devDependencies?.["@ast-grep/cli"], undefined);
	assert.equal(fs.existsSync(path.join(frontendDir, "sgconfig.yml")), false);
});
