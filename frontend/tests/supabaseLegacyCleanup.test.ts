import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(testDir, "..");
const repoRoot = path.resolve(frontendDir, "..");

function readText(relativePath: string): string {
	return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

test("project-level Supabase runtime leftovers are removed", () => {
	const packageJson = JSON.parse(
		fs.readFileSync(path.join(frontendDir, "package.json"), "utf8"),
	) as {
		dependencies?: Record<string, string>;
	};

	assert.equal(
		packageJson.dependencies?.["@supabase/supabase-js"],
		undefined,
	);
	assert.equal(packageJson.dependencies?.["miaoda-auth-react"], undefined);

	assert.equal(
		fs.existsSync(path.join(frontendDir, "src/shared/config/database.ts")),
		false,
	);
	assert.equal(
		fs.existsSync(path.join(frontendDir, "package-lock.json")),
		false,
	);
	assert.equal(
		fs.existsSync(path.join(repoRoot, "supabase/migrations/full_schema.sql")),
		false,
	);

	for (const scriptPath of [
		"scripts/setup.sh",
		"scripts/setup.js",
		"scripts/setup.bat",
		"scripts/check-setup.js",
	]) {
		assert.equal(fs.existsSync(path.join(repoRoot, scriptPath)), false, scriptPath);
	}
});

test("project docs and config no longer advertise Supabase setup", () => {
	const envExample = fs.readFileSync(
		path.join(frontendDir, ".env.example"),
		"utf8",
	);
	const architectureDoc = readText("docs/ARCHITECTURE.md");
	const agentArchitectureDoc = readText("docs/AGENT_AUDIT_ARCHITECTURE.md");
	const i18nMap = fs.readFileSync(
		path.join(frontendDir, "src/shared/i18n/offlineZhEnMap.generated.json"),
		"utf8",
	);

	assert.equal(envExample.includes("VITE_SUPABASE"), false);
	assert.equal(architectureDoc.includes("shared/config/database.ts"), false);
	assert.equal(agentArchitectureDoc.includes("PostgreSQL (Supabase)"), false);
	assert.equal(i18nMap.includes("Supabase 云端"), false);
	assert.equal(i18nMap.includes("Supabase cloud"), false);
});

test("frontend source imports the direct API layer instead of the legacy compatibility shim", () => {
	const sourceFiles = fs
		.readdirSync(path.join(frontendDir, "tests"), { withFileTypes: true })
		.filter((entry) => entry.isFile())
		.map((entry) => entry.name);

	assert.ok(sourceFiles.includes("supabaseLegacyCleanup.test.ts"));

	const importMatches = fs
		.readdirSync(path.join(frontendDir, "src"), { recursive: true })
		.filter((entry) => typeof entry === "string")
		.map((entry) => path.join(frontendDir, "src", entry))
		.filter((entry) => entry.endsWith(".ts") || entry.endsWith(".tsx"))
		.filter((entry) =>
			fs
				.readFileSync(entry, "utf8")
				.includes("@/shared/config/database"),
		);

	assert.deepEqual(importMatches, []);
});
