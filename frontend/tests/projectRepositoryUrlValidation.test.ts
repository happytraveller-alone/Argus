import test from "node:test";
import assert from "node:assert/strict";

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

test("validateProjectConfig rejects git ssh repository urls", async () => {
	const projectUtils = await importOrFail<any>("../src/shared/utils/projectUtils.ts");

	const validation = projectUtils.validateProjectConfig({
		name: "SSH Project",
		source_type: "repository",
		repository_url: "git@github.com:org/repo.git",
	});

	assert.equal(validation.valid, false);
	assert.deepEqual(validation.errors, ["仅支持 HTTPS 仓库地址，不再支持 SSH 地址"]);
});

test("validateProjectConfig rejects ssh scheme repository urls", async () => {
	const projectUtils = await importOrFail<any>("../src/shared/utils/projectUtils.ts");

	const validation = projectUtils.validateProjectConfig({
		name: "SSH Project",
		source_type: "repository",
		repository_url: "ssh://git@example.com/org/repo.git",
	});

	assert.equal(validation.valid, false);
	assert.deepEqual(validation.errors, ["仅支持 HTTPS 仓库地址，不再支持 SSH 地址"]);
});

test("validateProjectConfig keeps https repository urls valid", async () => {
	const projectUtils = await importOrFail<any>("../src/shared/utils/projectUtils.ts");

	const validation = projectUtils.validateProjectConfig({
		name: "HTTPS Project",
		source_type: "repository",
		repository_url: "https://github.com/org/repo.git",
	});

	assert.equal(validation.valid, true);
	assert.deepEqual(validation.errors, []);
});
