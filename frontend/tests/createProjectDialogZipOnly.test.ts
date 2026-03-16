import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

async function importOrFail<TModule = Record<string, unknown>>(
	relativePath: string,
): Promise<TModule> {
	try {
		return (await import(relativePath)) as TModule;
	} catch (error) {
		assert.fail(
			`expected helper module ${relativePath} to exist: ${error instanceof Error ? error.message : String(error)}`,
		);
	}
}

test("createEmptyProjectForm defaults to ZIP project semantics", async () => {
	const constants = await importOrFail<any>(
		"../src/pages/projects/constants.ts",
	);

	const form = constants.createEmptyProjectForm();

	assert.equal(form.source_type, "zip");
	assert.equal(form.repository_type, "other");
	assert.equal(form.repository_url, undefined);
	assert.equal(form.default_branch, "main");
});

test("CreateProjectDialog no longer exposes repository creation controls", () => {
	const filePath = path.resolve(
		process.cwd(),
		"src/pages/projects/components/CreateProjectDialog.tsx",
	);
	const source = fs.readFileSync(filePath, "utf8");

	assert.doesNotMatch(source, /onCreateRepositoryProject/);
	assert.doesNotMatch(source, /TabsTrigger value="repository"/);
	assert.doesNotMatch(source, /远程仓库/);
});
